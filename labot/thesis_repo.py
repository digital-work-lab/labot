from github import Github
import re
import os
import requests


# Create a pull-request with student details and word file, add issue-link in 
# When merged: notify student in comment
# When document signed: post in issue and close?

def parse_issue_body(issue_body):
    parsed_data = {}
    
    lines = issue_body.splitlines()
    
    for line in lines:
        if line.startswith("### "):
            current_key = line[4:].strip()
            parsed_data[current_key] = None
        elif line.strip():  # Skip empty lines
            if current_key:
                parsed_data[current_key] = line.strip()
    
    return parsed_data



def start_registration(issue_url):  
    g = Github(GITHUB_TOKEN)

    try:
        parts = issue_url.split("/")
        repo_name = f"{parts[3]}/{parts[4]}"  # owner/repo
        issue_number = int(parts[-1])
    except (IndexError, ValueError):
        print("Invalid issue URL format.")
        return

    # Retrieve the issue
    try:
        repo = g.get_repo(repo_name)
        issue = repo.get_issue(number=issue_number)
        print(f"Issue Title: {issue.title}")
        print(parse_issue_body(issue.body))

        # download all docx files from the repository
        # get all files in the repository
        files = repo.get_contents("")
        for file in files:
            if file.name.endswith(".docx"):
                print(f"Downloading file: {file.name}")
                file_content = file.decoded_content
                with open(file.name, "wb") as f:
                    f.write(file_content)

        issue.create_comment("Thank you. We have started the registration.")
        print("Comment added to the issue.")

    except Exception as e:
        print(f"An error occurred: {e}")


def list_registration_issues(GITHUB_TOKEN):
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    url = "https://api.github.com/user/repos"
    repos = []

    while url:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Failed to fetch repositories: {response.status_code}, {response.text}")
        repos.extend(response.json())
        url = response.links.get('next', {}).get('url')

    for repo in repos:
        print(f"Name: {repo['name']}, Full Name: {repo['full_name']}, Private: {repo['private']}")


def list_registration_issues_backup(GITHUB_TOKEN):
    g = Github(GITHUB_TOKEN)
    
    user = g.get_user()
    repos = user.get_repos()
    
    registration_issues = []

    print("Scanning repositories for '[registration]' issues...\n")

    for repo in repos:
        if not "thesis" in repo.full_name.lower():
            continue
        print(f"Checking repository: {repo.full_name}")
        try:
            issues = repo.get_issues(state="open")
            for issue in issues:
                if "[registration]" in issue.title.lower():
                    registration_issues.append({
                        "repository": repo.full_name,
                        "issue_title": issue.title,
                        "issue_url": issue.html_url
                    })
        except Exception as e:
            print(f"Error accessing repository {repo.full_name}: {e}")

    print()
    if registration_issues:
        print(f"Found {len(registration_issues)} issues with '[registration]' in the title:\n")
        for issue in registration_issues:
            print(f"- Repository: {issue['repository']}")
            print(f"  Title: {issue['issue_title']}")
            print(f"  URL: {issue['issue_url']}\n")
            print("TODO : REINCLUDE:")
            # start_registration(issue['issue_url'])
    else:
        print("No issues found with '[registration]' in the title.")

if __name__ == "__main__":
    # Note: this is executed regularly in
    # https://github.com/digital-work-lab/theses-confidential

    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
    if not GITHUB_TOKEN:
        raise EnvironmentError("The GITHUB_TOKEN environment variable is not set or empty.")



    list_registration_issues(GITHUB_TOKEN)
