import os
import re
import shutil
import argparse
import time
from git import Repo, GitCommandError
from github import Github, GithubException


def setup_argparse():
    parser = argparse.ArgumentParser(description="Process GitHub repositories")
    parser.add_argument(
        "--token", default=os.getenv("GITHUB_PERSONAL_TOKEN"), help="GitHub access token")
    parser.add_argument("--source-org", default="bio-tools",
                        help="Source organization name")
    parser.add_argument("--target-org", default="bio-agents",
                        help="Target organization name")
    parser.add_argument("--local-dir", default="./",
                        help="Local directory for repositories")
    parser.add_argument("--reprocess", action="store_true",
                        help="Reprocess existing repositories")
    return parser.parse_args()


def camel_to_kebab(name):
    if '-' in name:
        return name
    pattern = re.compile(r'(?<!^)(?=[A-Z][a-z]|(?<=[a-z])[A-Z])')
    parts = pattern.split(name)
    processed_parts = [part.lower() if not (
        part.isupper() and len(part) > 1) else part for part in parts]
    return '-'.join(processed_parts)


def replace_content(content):
    replacements = [
        (r"tools", "agents"), (r"Tools", "Agents"),
        (r"tool", "agent"), (r"Tool", "Agent"),
        (r"biotool", "bioagent"), (r"biotools", "bioagents"),
        (r"BioTools", "BioAgents"), (r"BioTool", "BioAgent"),
        (r"elixir", "iechor"), (r"Elixir", "iEchor"),
        (r"ELIXIR", "IECHOR"), (r"bio\.tools", "hub.bioagents.tech")
    ]
    for old, new in replacements:
        content = re.sub(old, new, content)
    return content


def is_binary(file_path):
    """Check if file is binary"""
    try:
        with open(file_path, 'tr') as check_file:
            check_file.read()
            return False
    except:
        return True


def process_directory(dir_path):
    for root, dirs, files in os.walk(dir_path, topdown=False):
        # Process directory names
        for dir_name in dirs:
            old_dir_path = os.path.join(root, dir_name)
            new_dir_name = replace_content(dir_name)
            new_dir_path = os.path.join(root, new_dir_name)
            if old_dir_path != new_dir_path:
                os.rename(old_dir_path, new_dir_path)
                print(f"Renamed directory: {old_dir_path} -> {new_dir_path}")

        # Process file names and content
        for file_name in files:
            old_file_path = os.path.join(root, file_name)
            new_file_name = replace_content(file_name)
            new_file_path = os.path.join(root, new_file_name)

            # Rename file (including binary files)
            if old_file_path != new_file_path:
                os.rename(old_file_path, new_file_path)
                print(f"Renamed file: {old_file_path} -> {new_file_path}")

            # Process file content (skip binary files)
            if not is_binary(new_file_path):
                try:
                    with open(new_file_path, 'r', encoding='utf-8') as file:
                        content = file.read()
                    new_content = replace_content(content)
                    if new_content != content:
                        with open(new_file_path, 'w', encoding='utf-8') as file:
                            file.write(new_content)
                        print(f"Updated content in: {new_file_path}")
                except UnicodeDecodeError:
                    print(
                        f"Skipped content replacement for non-UTF-8 file: {new_file_path}")
            else:
                print(f"Skipped content replacement for binary file: {new_file_path}")


def process_repo(repo, github_token, target_org_name, local_dir, reprocess=False):
    new_repo_name = camel_to_kebab(replace_content(repo.name))
    print(f"Original repo name: {repo.name}, New repo name: {new_repo_name}")

    local_repo_path = os.path.join(local_dir, new_repo_name)

    g = Github(github_token)
    target_org = g.get_organization(target_org_name)

    # Check if the repository exists in the target organization
    try:
        target_repo = target_org.get_repo(new_repo_name)
        if not reprocess:
            print(f"Repository {new_repo_name} already exists. Skipping.")
            return
        print(f"Repository {new_repo_name} exists. Reprocessing...")
        target_repo.delete()
        time.sleep(5)  # Wait for GitHub to process the deletion
    except GithubException:
        print(f"Repository {new_repo_name} does not exist in target organization. Creating...")

    # Create the repository in the target organization
    try:
        target_repo = target_org.create_repo(new_repo_name)
        print(f"Created new repository: {new_repo_name}")
        time.sleep(5)  # Wait for GitHub to process the creation
    except GithubException as e:
        print(f"Error creating repository {new_repo_name}: {str(e)}")
        return

    if os.path.exists(local_repo_path):
        shutil.rmtree(local_repo_path)

    Repo.clone_from(repo.clone_url, local_repo_path)
    # Remove the .git directory
    git_dir = os.path.join(local_repo_path, ".git")
    if os.path.exists(git_dir):
        shutil.rmtree(git_dir)

    process_directory(local_repo_path)

    # Initialize new git repository
    new_repo = Repo.init(local_repo_path)
    new_repo.git.add(A=True)
    new_repo.index.commit("Update content and rename")

    new_remote_url = f"https://{github_token}@github.com/{target_org_name}/{new_repo_name}.git"
    try:
        origin = new_repo.remote('origin')
        origin.set_url(new_remote_url)
    except ValueError:
        new_repo.create_remote('origin', new_remote_url)

    # Get the current branch name
    try:
        current_branch = new_repo.active_branch.name
    except TypeError:
        # If there's no active branch (empty repo), create one
        current_branch = "main"
        new_repo.git.checkout('-b', current_branch)

    # Push to the new repository with retry logic
    for attempt in range(3):  # Try up to 3 times
        try:
            new_repo.git.push("--force", "--set-upstream",
                             "origin", current_branch)
            print(f"Successfully pushed to {current_branch} branch: {new_repo_name}")
            break
        except GitCommandError as e:
            if attempt == 2:  # Last attempt
                print(f"Error pushing to repository {new_repo_name}: {str(e)}")
                return
            else:
                print(f"Push failed, retrying in 5 seconds...")
                time.sleep(5)
    try:
        target_repo = target_org.get_repo(new_repo_name)
        target_repo.add_to_collaborators("chenxingqiang", permission="admin")
        print(f"Added chenxingqiang as admin to {new_repo_name}")
    except Exception as e:
        print(f"Error adding collaborator to {new_repo_name}: {str(e)}")

    print(f"Processed and pushed: {new_repo_name}")


def main():
    args = setup_argparse()
    if not args.token:
        raise ValueError(
            "GitHub token not provided. Use --token or set GITHUB_TOKEN environment variable.")

    g = Github(args.token)
    source_org = g.get_organization(args.source_org)
    target_org = g.get_organization(args.target_org)

    if not args.reprocess:
        for repo in target_org.get_repos():
            if repo.name.lower() != ".github*":
                repo.delete()
        print("Existing repositories in target organization deleted.")

    for repo in source_org.get_repos():
        if repo.name.lower() == ".github*":
            continue
        try:
            process_repo(repo, args.token, args.target_org,
                         args.local_dir, args.reprocess)
        except Exception as e:
            print(f"Error processing {repo.name}: {str(e)}")


if __name__ == "__main__":
    main()
