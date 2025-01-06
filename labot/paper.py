import os
import re
import subprocess

import git
from openai import OpenAI


def clone_repository() -> None:
    repo_url = "https://github.com/digital-work-lab/paper-template"

    if os.listdir("."):
        print("Current directory is not empty")
        return

    try:
        git.Repo.clone_from(repo_url, ".")
        print("Repository cloned successfully")
    except git.GitCommandError as e:
        print(f"Error cloning repository: {e}")


def configure() -> str:
    title = input("Enter the title: ")
    authors = input("Enter the authors (comma-separated): ")
    abbreviation = input("Enter the project abbreviation: ")
    manuscript_repository = input("Enter the manuscript repository URL: ")

    with open("paper.md", "r+") as file:  # Open the file in read-write mode
        lines = file.readlines()  # Read all lines into a list
        file.seek(0)  # Move the file pointer to the beginning
        for line in lines:  # Iterate over the lines from the read mode
            if line.startswith("title:"):
                line = f'title: "{title}"\n'
            elif line.startswith("author:"):
                line = f'author: "{authors}"\n'
            elif line.startswith("project:"):
                line = "project:\n"
            elif line.startswith("  abbreviation:"):
                line = f"  abbreviation: {abbreviation}\n"
            elif line.startswith("  manuscriptrepository:"):
                line = f"  manuscriptrepository: {manuscript_repository}\n"
            file.write(line)

    print("Configuration completed successfully")
    return manuscript_repository


def setup() -> None:
    # Remove existing .git directory
    subprocess.run(["rm", "-rf", ".git"])

    # Initialize new git repository
    subprocess.run(["git", "init"])

    # Create necessary directories
    os.makedirs("analysis")
    os.makedirs("data")
    os.makedirs("figures")
    os.makedirs("output")

    # Install pre-commit hook
    subprocess.run(["pre-commit", "install"])

    # Copy post-checkout hook
    subprocess.run(["cp", "post-xxx-sample.txt", ".git/hooks/post-checkout"])
    subprocess.run(["cp", ".git/hooks/post-checkout", ".git/hooks/post-merge"])
    subprocess.run(["cp", ".git/hooks/post-checkout", ".git/hooks/post-commit"])

    # Remove post-xxx-sample.txt
    subprocess.run(["rm", "post-xxx-sample.txt"])

    # Add all files to git
    subprocess.run(["git", "add", "."])

    # Commit initial changes
    subprocess.run(["git", "commit", "-n", "-m", "initial commit"])

    # Run make pdf command
    subprocess.run(["make", "pdf"])


def push_repository(repository: str) -> None:

    repository = repository.replace("https://github.com/", "git@github.com:")
    if not repository.endswith(".git"):
        repository += ".git"

    subprocess.run(["git", "remote", "add", "origin", repository])
    subprocess.run(["git", "branch", "-M", "main"])
    subprocess.run(["git", "push", "-u", "origin", "main"])


def init() -> None:

    # return if current dir not empty
    if os.listdir("."):
        print("Current directory is not empty")
        return

    print("called")
    clone_repository()
    repository = configure()
    setup()
    if repository:
        push_repository(repository)


def split_into_chunks(text, max_chars=4000):
    """
    Split text into chunks that do not exceed max_chars, ensuring chunks are complete sentences.

    Args:
        text (str): The content to split.
        max_chars (int): Maximum number of characters per chunk.

    Returns:
        list: A list of text chunks.
    """
    chunks = []
    current_chunk = []

    for line in text.splitlines(keepends=True):
        if sum(len(s) for s in current_chunk) + len(line) <= max_chars:
            current_chunk.append(line)
        else:
            chunks.append("".join(current_chunk))
            current_chunk = [line]

    if current_chunk:
        chunks.append("".join(current_chunk))

    return chunks


def process_chunk(chunk, api_key):
    """
    Process a chunk of Markdown to suggest semantic line breaks while ignoring YAML headers and HTML comments.

    Args:
        chunk (str): The Markdown chunk to process.
        api_key (str): OpenAI API key.

    Returns:
        str: Revised chunk with semantic line breaks.
    """
    # Detect YAML header and HTML comments
    yaml_header_pattern = r"^---.*?---\s"  # YAML header is enclosed in "---"
    html_comment_pattern = r"<!--.*?-->"

    yaml_headers = re.findall(yaml_header_pattern, chunk, re.DOTALL)
    html_comments = re.findall(html_comment_pattern, chunk, re.DOTALL)

    # Remove YAML headers and HTML comments from the chunk
    sanitized_chunk = re.sub(yaml_header_pattern, "", chunk, flags=re.DOTALL)
    sanitized_chunk = re.sub(html_comment_pattern, "", sanitized_chunk, flags=re.DOTALL)

    # Define the prompt
    prompt = f'''
You are an expert in Markdown formatting. Revise the following Markdown content by introducing semantic line breaks.
Do not modify YAML headers, Latex tables, or HTML comments. Only introduce line breaks for lines longer than 160 characters, and ensure that no new line is shorter than 50 characters after the break.

Markdown content:
"""
{sanitized_chunk}
"""

Provide the revised content with semantic line breaks only:
'''

    client = OpenAI(api_key=api_key)

    try:
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert in Markdown and semantic formatting.",
                },
                {"role": "user", "content": prompt},
            ],
            model="gpt-4",
            max_tokens=1500,
            temperature=0.2,
        )
        revised_content = response.choices[0].message.content.strip()
    except Exception as e:
        return f"An error occurred: {e}"

    # Reinsert YAML headers and HTML comments
    for yaml_header in yaml_headers:
        revised_content = yaml_header + "\n" + revised_content
    for html_comment in html_comments:
        revised_content = html_comment + "\n" + revised_content

    return revised_content


def suggest_line_breaks(markdown_text, api_key):
    """
    Suggest semantic line breaks in a Markdown document using OpenAI's ChatGPT API.

    Args:
        markdown_text (str): The content of the Markdown file as a string.

    Returns:
        str: The suggested Markdown text with semantic line breaks.
    """
    chunks = split_into_chunks(markdown_text)
    # print('temp:')
    # chunks = [chunks[0]]
    revised_chunks = [process_chunk(chunk, api_key) for chunk in chunks]
    return "\n".join(revised_chunks)


def prep() -> None:

    api_key = os.getenv("OPENAI_KEY")
    if not api_key:
        raise OSError("OPENAI_KEY environment variable is not set.")

    with open("paper.md") as file:
        markdown_content = file.read()

    revised_content = suggest_line_breaks(markdown_content, api_key)

    with open("paper.md", "w") as file:
        file.write(revised_content)
