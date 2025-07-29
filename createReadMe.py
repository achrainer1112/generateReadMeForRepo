import os
import requests
import subprocess
import sys
import tiktoken  # For token counting 

# Define folders to be excluded from consideration
exclude_folders = ['.git', 'node_modules', 'build', 'dist', 'gradle']

# Function to read a file and return its contents as a string
def read_file(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            return file.read()
    else:
        print(f"File not found: {file_path}")
        return ""

# Function to send a request to the AI API with chunking support
def send_to_ai_chunked(api_url, api_key, text, max_tokens=100000):
    """
    Send text to AI API, chunking if necessary to avoid token limits
    """
    tokenizer = tiktoken.get_encoding("cl100k_base")
    tokens = tokenizer.encode(text)
    
    if len(tokens) <= max_tokens:
        # Text fits in one request
        return send_to_ai(api_url, api_key, text)
    
    # Need to chunk the text
    print(f"Text too long ({len(tokens)} tokens), chunking into smaller parts...")
    
    # Split into chunks
    chunks = []
    chunk_size = max_tokens - 1000  # Leave room for prompt overhead
    
    for i in range(0, len(tokens), chunk_size):
        chunk_tokens = tokens[i:i + chunk_size]
        chunk_text = tokenizer.decode(chunk_tokens)
        chunks.append(chunk_text)
    
    # Process each chunk and combine responses
    responses = []
    for i, chunk in enumerate(chunks):
        print(f"Processing chunk {i+1}/{len(chunks)}...")
        chunk_prompt = f"""This is part {i+1} of {len(chunks)} of a repository analysis. 
Please analyze this part and provide insights. If this is not the last part, focus on individual file analysis.
If this is the last part (part {len(chunks)}), please provide a comprehensive summary.

{chunk}"""
        
        response = send_to_ai(api_url, api_key, chunk_prompt)
        if 'error' not in response:
            responses.append(response['choices'][0]['message']['content'])
        else:
            responses.append(f"Error processing chunk {i+1}: {response['error']['message']}")
    
    # Combine all responses
    combined_response = {
        'choices': [{
            'message': {
                'content': "\n\n".join([f"## Part {i+1}\n{resp}" for i, resp in enumerate(responses)])
            }
        }]
    }
    
    return combined_response

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
        'README.md', 'readme.md', 'README.txt',
        'package.json', 'requirements.txt', 'Cargo.toml', 'pom.xml',
        'Dockerfile', 'docker-compose.yml',
        '.env.example', 'config.py', 'settings.py'
    ]
    
    # Important extensions to prioritize
    important_extensions = ['.py', '.js', '.ts', '.java', '.cpp', '.c', '.rs', '.go']
    
    # Skip very large files (over 50KB)
    try:
        if os.path.getsize(file_path) > 50000:
            print(f"Skipping large file: {file_path}")
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
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico',
        '.pdf', '.zip', '.tar', '.gz', '.exe', '.dll',
        '.so', '.dylib', '.class', '.jar'
    ]
    
    if ext.lower() in skip_extensions:
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

    # Read the prompt from prompt.txt in the workflow repository (corrected path)
    script_repo_path = os.path.join(os.getcwd(), 'workflow-repo')  # Changed from 'generateReadMeForRepo'
    prompt_file_path = os.path.join(script_repo_path, 'prompt.txt')
    prompt_text = read_file(prompt_file_path)

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

    affected_files.append(prompt_file_path)
    total_characters += len(prompt_text)

    # Prepare the prompt with contents of additional files (with smart filtering)
    for root, dirs, filenames in os.walk(cloned_repo_path):
        # Remove directories that should be excluded
        dirs[:] = [d for d in dirs if not is_excluded_folder(os.path.join(root, d))]
        for filename in filenames:
            file_path = os.path.join(root, filename)
            
            # Check if we should include this file
            if not should_include_file(file_path, filename):
                skipped_files.append(file_path)
                continue
                
            try:
                # Read file content and append it to the prompt
                file_content = read_file(file_path)
                
                # Limit individual file content to prevent huge files
                if len(file_content) > 10000:  # Limit to ~10KB per file
                    file_content = file_content[:10000] + "\n... (file truncated)"
                
                prompt_text += f"\n\n### Content of {file_path}:\n{file_content}"
                affected_files.append(file_path)
                total_characters += len(file_content)
                
                # Stop if we're getting too large
                if count_tokens(prompt_text) > 150000:  # Conservative limit
                    print("Prompt getting too large, stopping file collection")
                    break
                    
            except Exception as e:
                print(f"Error reading the file {file_path}: {e}")

    # Ensure prompt_text is encoded in utf-8
    prompt_text = prompt_text.encode('utf-8', errors='ignore').decode('utf-8')

    token_count = count_tokens(prompt_text)
    
    if dry_run == 'true':
        # Print summary for dry run
        print("Summary (Dry Run):")
        print(f"Affected Files and Paths:")
        for file in affected_files:
            print(f"- {file}")
        print(f"Skipped Files:")
        for file in skipped_files:
            print(f"- {file}")
        print(f"Total Characters in Prompt Text: {total_characters}")
        print(f"Token count for model: {token_count}")
        print("Note: No AI request or repo changes are made.")
    else:
        try:
            # Send the combined text to the AI and get the response (with chunking if needed)
            response = send_to_ai_chunked(api_url, api_key, prompt_text)

            if 'error' in response:
                # Extract and print the error message
                error_message = response['error']['message']
                print(f'Error processing the request: {error_message}')
                # Write the error message to the ReadMe file
                write_to_readme(os.path.join(cloned_repo_path, 'README.md'), repo_name, error_message)
                if 'quota' in error_message:
                    print("API quota reached. Process is terminated.")
            else:
                # Extract the AI message
                ai_message = response['choices'][0]['message']['content']

                # Write the AI response to the ReadMe file
                write_to_readme(os.path.join(cloned_repo_path, 'README.md'), repo_name, ai_message)

        except Exception as e:
            print(f"Error sending the request to AI: {e}")

        print(f"Process completed for repository: {repo_name}. AI responses or errors were written to the ReadMe file.")


# Execute the main program
if __name__ == '__main__':
    main()
