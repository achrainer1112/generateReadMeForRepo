import os
import requests
import subprocess
import sys
import tiktoken  # For token counting 

# Define folders to be excluded from consideration
exclude_folders = ['.git', 'node_modules', 'build', 'dist', 'gradle', '__pycache__', '.pytest_cache']

# Function to read a file and return its contents as a string
def read_file(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            return file.read()
    else:
        print(f"File not found: {file_path}")
        return ""

# Function to send a request to the AI API
def send_to_ai(api_url, api_key, text):
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    data = {
        'model': 'gpt-4o-mini',
        'messages': [{'role': 'user', 'content': text}],
        'max_tokens': 2048
    }
    response = requests.post(api_url, headers=headers, json=data)
    return response.json()

# Function to write the AI response or error message to the ReadMe file
def write_to_readme(readme_path, repo_name, content):
    try:
        with open(readme_path, 'w', encoding='utf-8') as readme_file:
            readme_file.write(f"# {repo_name}\n")
            readme_file.write(content)
    except Exception as e:
        print(f"Error writing to the ReadMe file: {e}")

# Function to get subfolders to exclude from consideration
def is_excluded_folder(path):
    while path != os.path.dirname(path):  
        if os.path.basename(path) in exclude_folders:
            return True
        path = os.path.dirname(path)
    return False

# Function to count tokens 
def count_tokens(text):
    tokenizer = tiktoken.get_encoding("cl100k_base")
    return len(tokenizer.encode(text))

# Function to prioritize important files and limit content
def should_include_file(file_path, filename):
    """
    Determine if a file should be included based on importance and size
    """
    # Always include these important files
    important_files = [
        'README.md', 'readme.md', 'README.txt', 'README.rst',
        'package.json', 'requirements.txt', 'Cargo.toml', 'pom.xml',
        'Dockerfile', 'docker-compose.yml', 'docker-compose.yaml',
        '.env.example', 'config.py', 'settings.py', 'main.py', 'app.py',
        'index.js', 'index.ts', 'server.js', 'app.js',
        'LICENSE', 'CHANGELOG.md', 'CONTRIBUTING.md'
    ]
    
    # Important extensions to prioritize
    important_extensions = [
        '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h',
        '.rs', '.go', '.php', '.rb', '.cs', '.swift', '.kt', '.scala',
        '.html', '.css', '.scss', '.less', '.vue', '.svelte',
        '.yml', '.yaml', '.json', '.xml', '.toml', '.ini', '.cfg',
        '.md', '.txt', '.rst'
    ]
    
    # Skip very large files (over 50KB)
    try:
        if os.path.getsize(file_path) > 50000:
            print(f"Skipping large file: {file_path} (size: {os.path.getsize(file_path)} bytes)")
            return False
    except OSError:
        return False
    
    # Always include important files
    if filename in important_files:
        return True
    
    # Include files with important extensions
    _, ext = os.path.splitext(filename)
    if ext.lower() in important_extensions:
        return True
    
    # Skip binary files and other non-text files
    skip_extensions = [
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.svg',
        '.pdf', '.zip', '.tar', '.gz', '.rar', '.7z',
        '.exe', '.dll', '.so', '.dylib', '.class', '.jar',
        '.woff', '.woff2', '.ttf', '.eot', '.otf',
        '.mp4', '.mp3', '.wav', '.avi', '.mov'
    ]
    
    if ext.lower() in skip_extensions:
        return False
    
    # Skip files that are typically auto-generated or not useful for documentation
    skip_patterns = [
        'package-lock.json', 'yarn.lock', 'Cargo.lock',
        '.DS_Store', 'Thumbs.db', '.gitignore', '.gitattributes'
    ]
    
    if filename in skip_patterns:
        return False
    
    return True

def main():
    if len(sys.argv) < 3:
        print("Error: Missing repository name argument.")
        return

    repo_name = sys.argv[1]
    dry_run = sys.argv[2]
    repo_url = f"https://github.com/achrainer1112/{repo_name}.git"

    # Clone the repository using 'gh'
    try:
        subprocess.run(['gh', 'repo', 'clone', repo_url], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error cloning the repository: {e}")
        return

    # Path to the cloned repository
    cloned_repo_path = os.path.join(os.getcwd(), repo_name)

    # Read the prompt from prompt.txt in the workflow repository (FIXED PATH)
    script_repo_path = os.path.join(os.getcwd(), 'workflow-repo')
    prompt_file_path = os.path.join(script_repo_path, 'prompt.txt')
    prompt_text = read_file(prompt_file_path)

    if not prompt_text:
        print("Error: Could not read prompt.txt file")
        return

    # AI API information
    api_url = 'https://api.openai.com/v1/chat/completions'
    api_key = os.getenv('OPENAI_API_KEY')  # Load API key from environment variables

    if not api_key:
        print("Error: Environment variable OPENAI_API_KEY is not set")
        return
    
    # Collect file details for summary
    affected_files = []
    total_characters = 0
    skipped_files = []
    truncated_files = []

    affected_files.append(prompt_file_path)
    total_characters += len(prompt_text)

    # Track token count to avoid API limits
    max_tokens = 120000  # Conservative limit for gpt-4o-mini
    
    print(f"Processing repository: {repo_name}")
    print(f"Starting token count: {count_tokens(prompt_text)}")

    # Prepare the prompt with contents of additional files (with smart filtering)
    files_processed = 0
    for root, dirs, filenames in os.walk(cloned_repo_path):
        # Remove directories that should be excluded
        dirs[:] = [d for d in dirs if not is_excluded_folder(os.path.join(root, d))]
        
        for filename in filenames:
            file_path = os.path.join(root, filename)
            relative_path = os.path.relpath(file_path, cloned_repo_path)
            
            # Check if we should include this file
            if not should_include_file(file_path, filename):
                skipped_files.append(relative_path)
                continue
                
            try:
                # Read file content
                file_content = read_file(file_path)
                if not file_content:
                    continue
                
                # Limit individual file content to prevent huge files
                original_length = len(file_content)
                if len(file_content) > 8000:  # Limit to ~8KB per file
                    file_content = file_content[:8000] + "\n... (file truncated due to size)"
                    truncated_files.append(f"{relative_path} (original: {original_length} chars)")
                
                # Create file entry
                file_entry = f"\n\n### Content of {relative_path}:\n{file_content}"
                
                # Check if adding this file would exceed token limit
                test_prompt = prompt_text + file_entry
                if count_tokens(test_prompt) > max_tokens:
                    print(f"Token limit would be exceeded, stopping at {files_processed} files")
                    skipped_files.append(f"{relative_path} (stopped due to token limit)")
                    break
                
                # Add file to prompt
                prompt_text += file_entry
                affected_files.append(relative_path)
                total_characters += len(file_content)
                files_processed += 1
                
                # Progress update every 10 files
                if files_processed % 10 == 0:
                    current_tokens = count_tokens(prompt_text)
                    print(f"Processed {files_processed} files, current tokens: {current_tokens}")
                    
            except Exception as e:
                print(f"Error reading the file {file_path}: {e}")
                skipped_files.append(f"{relative_path} (error: {str(e)})")

    # Ensure prompt_text is encoded in utf-8
    prompt_text = prompt_text.encode('utf-8', errors='ignore').decode('utf-8')
    final_token_count = count_tokens(prompt_text)
    
    print(f"Final processing stats:")
    print(f"- Files processed: {files_processed}")
    print(f"- Files skipped: {len(skipped_files)}")
    print(f"- Files truncated: {len(truncated_files)}")
    print(f"- Final token count: {final_token_count}")
    
    if dry_run == 'true':
        # Print detailed summary for dry run
        print("\n" + "="*50)
        print("DETAILED DRY RUN SUMMARY")
        print("="*50)
        print(f"Repository: {repo_name}")
        print(f"Total characters in prompt: {total_characters:,}")
        print(f"Final token count: {final_token_count:,}")
        print(f"Token limit: {max_tokens:,}")
        
        print(f"\nPROCESSED FILES ({len(affected_files)}):")
        for file in affected_files:
            print(f"  ✓ {file}")
        
        if truncated_files:
            print(f"\nTRUNCATED FILES ({len(truncated_files)}):")
            for file in truncated_files:
                print(f"  ✂ {file}")
        
        if skipped_files:
            print(f"\nSKIPPED FILES ({len(skipped_files)}):")
            for file in skipped_files[:20]:  # Show first 20 skipped files
                print(f"  ⏭ {file}")
            if len(skipped_files) > 20:
                print(f"  ... and {len(skipped_files) - 20} more")
        
        print(f"\nEstimated API cost: ~${(final_token_count / 1000000) * 0.15:.4f}")
        print("(Note: No AI request or repo changes are made in dry run)")
        
    else:
        if final_token_count > max_tokens:
            print(f"WARNING: Token count ({final_token_count}) exceeds safe limit ({max_tokens})")
            print("Consider running with more aggressive filtering or chunking")
        
        try:
            print("Sending request to AI API...")
            # Send the combined text to the AI and get the response
            response = send_to_ai(api_url, api_key, prompt_text)

            if 'error' in response:
                # Extract and print the error message
                error_message = response['error']['message']
                print(f'Error processing the request: {error_message}')
                # Write the error message to the ReadMe file
                write_to_readme(os.path.join(cloned_repo_path, 'README.md'), repo_name, 
                              f"\n## Error\n\n{error_message}\n\n*Generated at token count: {final_token_count}*")
                if 'quota' in error_message.lower():
                    print("API quota reached. Process is terminated.")
            else:
                # Extract the AI message
                ai_message = response['choices'][0]['message']['content']
                
                # Add generation info
                generation_info = f"\n\n---\n*README generated from {files_processed} files ({final_token_count:,} tokens)*"
                full_content = ai_message + generation_info

                # Write the AI response to the ReadMe file
                write_to_readme(os.path.join(cloned_repo_path, 'README.md'), repo_name, full_content)
                print("✅ README.md successfully generated!")

        except Exception as e:
            print(f"Error sending the request to AI: {e}")
            # Write error to README
            write_to_readme(os.path.join(cloned_repo_path, 'README.md'), repo_name, 
                          f"\n## Generation Error\n\n{str(e)}\n\n*Failed at token count: {final_token_count}*")

        print(f"Process completed for repository: {repo_name}")


# Execute the main program
if __name__ == '__main__':
    main()
