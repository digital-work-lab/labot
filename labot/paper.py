
import os
import git
import subprocess

def clone_repository() -> None:
    repo_url = "https://github.com/digital-work-lab/paper-template"

    if os.listdir('.'):
        print('Current directory is not empty')
        return

    try:
        git.Repo.clone_from(repo_url, '.')
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
                line = f"title: \"{title}\"\n"
            elif line.startswith("author:"):
                line = f"author: \"{authors}\"\n"
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
    subprocess.run( ["git", "branch", "-M", "main"])
    subprocess.run(["git", "push", "-u", "origin", "main"])

def init() -> None:

    # return if current dir not empty
    if os.listdir('.'):
        print('Current directory is not empty')
        return

    print('called')
    clone_repository()
    repository = configure()
    setup()
    if repository:
        push_repository(repository)