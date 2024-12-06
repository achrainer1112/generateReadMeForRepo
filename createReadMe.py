import os
import requests
import subprocess
import sys

# Define folders to be excluded from consideration
exclude_folders = ['.git', 'node_modules', 'build', 'dist', 'gradle', '.asm', '.prt', '.png']

# Function to read a file and return its contents as a string
def read_file(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            return file.read()
    else:
        print(f"File not found: {file_path}")
        return ""

# Function to send a request to the aimlapi.com API
def send_to_ai(api_url, api_key, text):
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    data = {
        'model': 'google/gemma-2b-it',  # Neues Modell
        'prompt': text,
        'max_tokens': 2048,
        'temperature': 0.7  # Optional: Beeinflusst die Kreativität der AI
    }
    try:
        response = requests.post(api_url, headers=headers, json=data)
        response.raise_for_status()  # Überprüft, ob die Anfrage erfolgreich war
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Fehler bei der Anfrage: {e}")
        return {"error": str(e)}

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

def main():
    if len(sys.argv) < 3:
        print("Error: Missing repository name argument.")
        return

    repo_name = sys.argv[1]
    dry_run = sys.argv[2]
    repo_url = f"https://github.com/achrainer1112/{repo_name}.git"

    # Clone the repository using 'gh'
    try:
        # Read the prompt from prompt.txt in the script repository
        prompt_file_path = os.path.join(os.getcwd(), 'prompt.txt')
        prompt_text = read_file(prompt_file_path)
        
        subprocess.run(['gh', 'repo', 'clone', repo_url], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error cloning the repository: {e}")
        return

    # Path to the cloned repository
    cloned_repo_path = os.path.join(os.getcwd(), repo_name)

    # AI API information
    api_url = 'https://api.aimlapi.com/v1/completions'  # Endpoint von aimlapi.com
    api_key = os.getenv('AIMLAPI_API_KEY')  # Lade den API-Key aus den Umgebungsvariablen

    if not api_key:
        print("Error: Environment variable AIMLAPI_API_KEY is not set")
        return
    
    # Collect file details for summary
    affected_files = []
    total_characters = 0

    affected_files.append(prompt_file_path)
    total_characters += len(prompt_text)

    # Prepare the prompt with contents of additional files
    for root, dirs, filenames in os.walk(cloned_repo_path):
        # Remove directories that should be excluded
        dirs[:] = [d for d in dirs if not is_excluded_folder(os.path.join(root, d))]
        for filename in filenames:
            file_path = os.path.join(root, filename)
            try:
                # Read file content and append it to the prompt
                file_content = read_file(file_path)
                prompt_text += f"\n\n### Content of {file_path}:\n{file_content}"
                affected_files.append(file_path)
                total_characters += len(file_content)
            except Exception as e:
                print(f"Error reading the file {file_path}: {e}")

    if dry_run == 'true':
        # Print summary for dry run
        print("Summary (Dry Run):")
        print(f"Affected Files and Paths:")
        for file in affected_files:
            print(f"- {file}")
        print(f"Total Characters in Prompt Text: {total_characters}")
        print("Note: No AI request or repo changes are made.")
    else:
        try:
            # Send the combined text to the AI and get the response
            response = send_to_ai(api_url, api_key, prompt_text)

            if 'error' in response:
                # Extract and print the error message
                error_message = response['error']
                print(f'Error processing the request: {error_message}')
                # Write the error message to the ReadMe file
                write_to_readme(os.path.join(cloned_repo_path, 'README.md'), repo_name, error_message)
            else:
                # Extract the AI message
                ai_message = response.get('completion', 'No completion returned.')

                # Write the AI response to the ReadMe file
                write_to_readme(os.path.join(cloned_repo_path, 'README.md'), repo_name, ai_message)

        except Exception as e:
            print(f"Error sending the request to AI: {e}")

        print(f"Process completed for repository: {repo_name}. AI responses or errors were written to the ReadMe file.")

# Execute the main program
if __name__ == '__main__':
    main()
