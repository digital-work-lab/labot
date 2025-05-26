import os
import requests
import csv

class GitHubAccessReporter:
    def __init__(self, org):
        self.GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
        self.ORG = org
        self.headers = {
            "Authorization": f"token {self.GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }

    def get_paginated(self, url):
        results = []
        while url:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            results.extend(response.json())
            url = response.links.get('next', {}).get('url')
        return results

    def get_repos(self):
        url = f"https://api.github.com/orgs/{self.ORG}/repos?per_page=100"
        return self.get_paginated(url)

    def get_collaborators(self, repo_name):
        url = f"https://api.github.com/repos/{self.ORG}/{repo_name}/collaborators?per_page=100"
        return self.get_paginated(url)

    def get_teams(self):
        url = f"https://api.github.com/orgs/{self.ORG}/teams?per_page=100"
        return self.get_paginated(url)

    def get_team_repos(self, team_slug):
        url = f"https://api.github.com/orgs/{self.ORG}/teams/{team_slug}/repos?per_page=100"
        return self.get_paginated(url)

    def generate_report(self, filename="access_report.csv"):
        rows = []

        # Individual collaborators per repo
        for repo in self.get_repos():
            repo_name = repo["name"]
            collaborators = self.get_collaborators(repo_name)
            for user in collaborators:
                login = user["login"]
                permissions = user.get("permissions", {})
                for perm, has_perm in permissions.items():
                    if has_perm:
                        rows.append([repo_name, login, "user", perm])

        # Team access per repo
        for team in self.get_teams():
            team_slug = team["slug"]
            repos = self.get_team_repos(team_slug)
            for repo in repos:
                repo_name = repo["name"]
                permissions = repo.get("permissions", {})
                for perm, has_perm in permissions.items():
                    if has_perm:
                        rows.append([repo_name, team_slug, "team", perm])

        # Write CSV
        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Repository", "User/Team", "Type", "Permission"])
            writer.writerows(rows)

        print(f"✅ Report saved to {filename}")


if __name__ == "__main__":
    reporter = GitHubAccessReporter("digital-work-lab")
    reporter.generate_report()
