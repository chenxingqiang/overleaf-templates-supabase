import os
import subprocess
import argparse
from git import Repo
from github import Github


def run_command(command):
    """执行 shell 命令并返回输出"""
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    output, error = process.communicate()
    if process.returncode != 0:
        print(f"Error executing command: {command}")
        print(f"Error message: {error.decode('utf-8')}")
    return output.decode('utf-8').strip()


def is_repo_clean(repo_path):
    """检查 git 仓库是否有未提交的更改"""
    repo = Repo(repo_path)
    return not repo.is_dirty()


def rename_and_replace(repo_path, old_str, new_str):
    """重命名文件/文件夹并替换文件内容"""
    # 重命名文件和文件夹
    rename_cmd = f"find {repo_path} -depth -name '*{old_str}*' -execdir rename 's/{old_str}/{new_str}/g' '{{}}' +"
    run_command(rename_cmd)

    # 替换文件内容
    replace_cmd = f"grep -rl '{old_str}' {repo_path} | xargs sed -i 's/{old_str}/{new_str}/g'"
    run_command(replace_cmd)


def process_repo(repo_name, old_str, new_str, github_token, org_name):
    """处理单个仓库"""
    g = Github(github_token)
    org = g.get_organization(org_name)

    local_path = f"./{repo_name}"

    if os.path.exists(local_path):
        print(f"Local repository {repo_name} found.")
        if not is_repo_clean(local_path):
            print(f"Local repository {repo_name} has uncommitted changes. Skipping.")
            return
    else:
        print(f"Cloning repository {repo_name}...")
        repo_url = f"https://github.com/{org_name}/{repo_name}.git"
        Repo.clone_from(repo_url, local_path)

    print(f"Processing repository: {repo_name}")
    rename_and_replace(local_path, old_str, new_str)

    # 提交更改
    repo = Repo(local_path)
    repo.git.add(A=True)
    repo.index.commit(f"Replace '{old_str}' with '{new_str}'")

    # 推送更改
    origin = repo.remote(name='origin')
    origin.push()

    print(f"Changes pushed to repository: {repo_name}")


def process_organization(old_str, new_str, github_token, org_name, single_repo=None):
    """处理组织中的所有仓库或单个指定的仓库"""
    g = Github(github_token)
    org = g.get_organization(org_name)

    if single_repo:
        repos = [org.get_repo(single_repo)]
    else:
        repos = org.get_repos()

    for repo in repos:
        if repo.name.lower() != ".github":
            try:
                process_repo(repo.name, old_str, new_str,
                            github_token, org_name)
            except Exception as e:
                print(f"Error processing repository {repo.name}: {str(e)}")
        else:
            print(f"Skipping .github repository")


def main():
    parser = argparse.ArgumentParser(
        description="Replace content in GitHub repositories.")
    parser.add_argument("old_str", help="String to be replaced")
    parser.add_argument("new_str", help="String to replace with")
    parser.add_argument(
        "--repo", help="Name of a specific repository to process (optional)")
    parser.add_argument(
        "--token", help="GitHub personal access token (optional, can be set via GITHUB_TOKEN env variable)")
    parser.add_argument(
        "--org", help="GitHub organization name", required=True)

    args = parser.parse_args()

    # 首选从环境变量获取 token，如果没有则使用命令行参数
    github_token = access_token = os.getenv(
        "GITHUB_PERSONAL_TOKEN") or args.token

    if not github_token:
        raise ValueError(
            "GitHub token must be provided either via GITHUB_TOKEN environment variable or --token argument")

    process_organization(args.old_str, args.new_str,
                        github_token, args.org, args.repo)


if __name__ == "__main__":
    main()
