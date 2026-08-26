import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import requests
import subprocess
import tempfile
import os
import shutil
import re
import threading
import time
import json
from urllib.parse import urlparse, quote
from datetime import datetime
import certifi
import urllib3

# 禁用 SSL 警告（用于降级重试时）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

GITEE_API_BASE = "https://gitee.com/api/v5"
GITHUB_API_BASE = "https://api.github.com"

# 创建全局会话，默认使用 certifi 的 CA 证书
session = requests.Session()
session.verify = certifi.where()

def run_git(args, cwd=None):
    """执行 git 命令并返回输出"""
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode, result.stdout

def safe_request(method, url, retries=3, backoff=2, **kwargs):
    """发送请求，自动重试"""
    if "github.com" in url or "api.github.com" in url:
        verify = kwargs.pop("verify", session.verify)
        for attempt in range(retries):
            try:
                resp = session.request(method, url, verify=verify, **kwargs)
                if resp.status_code >= 500:
                    raise requests.exceptions.RequestException(f"5xx error: {resp.status_code}")
                return resp
            except requests.exceptions.SSLError:
                if attempt == retries - 1:
                    raise
                verify = False
                time.sleep(backoff)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.RequestException) as e:
                if attempt == retries - 1:
                    raise
                time.sleep(backoff)
    else:
        for attempt in range(retries):
            try:
                resp = session.request(method, url, **kwargs)
                if resp.status_code >= 500:
                    raise requests.exceptions.RequestException(f"5xx error: {resp.status_code}")
                return resp
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                if attempt == retries - 1:
                    raise
                time.sleep(backoff)
    raise RuntimeError("Request failed")

def get_gitee_username(token):
    url = f"{GITEE_API_BASE}/user"
    params = {"access_token": token}
    resp = safe_request("GET", url, params=params, timeout=10)
    if resp.status_code == 200:
        return resp.json()["login"]
    else:
        raise Exception(f"获取用户信息失败: {resp.status_code} {resp.text}")

def create_gitee_repo(token, name, private, description=""):
    url = f"{GITEE_API_BASE}/user/repos"
    data = {
        "access_token": token,
        "name": name,
        "private": private,
        "description": description,
        "auto_init": False,
    }
    resp = safe_request("POST", url, data=data, timeout=15)
    if resp.status_code == 201:
        return resp.json()
    else:
        raise Exception(f"创建 Gitee 仓库失败: {resp.status_code} {resp.text}")

def check_repo_exists(token, owner, repo):
    url = f"{GITEE_API_BASE}/repos/{owner}/{repo}"
    params = {"access_token": token}
    resp = safe_request("GET", url, params=params, timeout=10)
    if resp.status_code == 200:
        return True
    elif resp.status_code == 404:
        return False
    else:
        raise Exception(f"检查仓库失败: {resp.status_code} {resp.text}")

def extract_repo_name(github_url):
    url = github_url.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    if url.startswith("https://") or url.startswith("http://"):
        path = urlparse(url).path
        parts = path.strip("/").split("/")
        if len(parts) >= 2:
            return parts[-1]
    elif url.startswith("git@github.com:"):
        path = url.split(":", 1)[1]
        parts = path.split("/")
        if len(parts) >= 2:
            return parts[-1]
    raise Exception("无法从 GitHub URL 中提取仓库名，请手动填写")

def extract_github_owner_repo(github_url):
    url = github_url.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    if url.startswith("https://") or url.startswith("http://"):
        path = urlparse(url).path
        parts = path.strip("/").split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]
    elif url.startswith("git@github.com:"):
        path = url.split(":", 1)[1]
        parts = path.split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]
    raise Exception("无法从 GitHub URL 中提取仓库信息")

def get_github_repo_info(owner, repo):
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}"
    resp = safe_request("GET", url, timeout=15)
    if resp.status_code == 200:
        data = resp.json()
        return data.get("description", ""), data.get("homepage", "")
    else:
        raise Exception(f"获取 GitHub 仓库信息失败: {resp.status_code} {resp.text}")

def update_gitee_repo_info(token, owner, repo, description, homepage, log_func):
    url = f"{GITEE_API_BASE}/repos/{owner}/{repo}"
    data = {
        "access_token": token,
        "name": repo,
        "description": description or "",
        "homepage": homepage or "",
    }
    resp = safe_request("PATCH", url, data=data, timeout=15)
    if resp.status_code == 200:
        log_func("仓库简介同步成功")
        return True
    else:
        log_func(f"更新仓库简介失败: {resp.status_code} {resp.text}")
        return False

def get_github_releases(owner, repo):
    releases = []
    page = 1
    while True:
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/releases"
        params = {"per_page": 100, "page": page}
        resp = safe_request("GET", url, params=params, timeout=20)
        if resp.status_code != 200:
            raise Exception(f"获取 GitHub Releases 失败: {resp.status_code} {resp.text}")
        data = resp.json()
        if not data:
            break
        releases.extend(data)
        page += 1
    return releases

def get_gitee_releases(token, owner, repo, log_func=None):
    url = f"{GITEE_API_BASE}/repos/{owner}/{repo}/releases"
    params = {"access_token": token, "per_page": 100}
    resp = safe_request("GET", url, params=params, timeout=15)
    if resp.status_code == 200:
        return resp.json()
    else:
        if log_func:
            log_func(f"获取 Gitee Releases 失败: {resp.status_code} {resp.text}")
        return []

def download_file(url, dest_path, log_func=None):
    for attempt in range(3):
        try:
            resp = safe_request("GET", url, stream=True, timeout=60)
            resp.raise_for_status()
            with open(dest_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return True
        except Exception as e:
            if log_func:
                log_func(f"下载失败 (尝试 {attempt+1}/3): {url} - {e}")
            if attempt == 2:
                return False
            time.sleep(5)
    return False

def create_gitee_release(token, owner, repo, tag_name, name, body, target_commitish, log_func):
    url = f"{GITEE_API_BASE}/repos/{owner}/{repo}/releases"
    data = {
        "access_token": token,
        "tag_name": tag_name,
        "name": name,
        "body": body,
        "target_commitish": target_commitish,
    }
    resp = safe_request("POST", url, data=data, timeout=15)
    if resp.status_code in (201, 200):
        return resp.json()
    else:
        log_func(f"创建 Gitee Release 失败: {resp.status_code} {resp.text}")
        return None

def version_key(tag):
    tag = tag.lower()
    if tag.startswith('v'):
        tag = tag[1:]
    parts = re.split(r'[.\-+]', tag)
    key = []
    for p in parts:
        if p.isdigit():
            key.append(int(p))
        else:
            key.append(p)
    return key

def migrate_releases(github_url, token, repo_name, repo_git_dir, assets_base_dir, log_func):
    owner, repo = extract_github_owner_repo(github_url)
    username = get_gitee_username(token)

    log_func("开始迁移 GitHub Releases...")
    releases = get_github_releases(owner, repo)
    if not releases:
        log_func("没有发现任何 Release")
        return

    try:
        releases.sort(key=lambda r: version_key(r.get("tag_name", "")))
        log_func(f"共发现 {len(releases)} 个 Release，已按版本号排序")
    except Exception as e:
        log_func(f"版本号排序失败，保持原有顺序: {e}")

    if assets_base_dir:
        base_dir = os.path.join(assets_base_dir, repo_name)
    else:
        home_dir = os.path.expanduser("~")
        base_dir = os.path.join(home_dir, "gitee_release_assets", repo_name)
    os.makedirs(base_dir, exist_ok=True)

    existing_releases = get_gitee_releases(token, username, repo_name, log_func)
    existing_tags = {r.get("tag_name") for r in existing_releases}

    for release in releases:
        tag = release.get("tag_name", "")
        name = release.get("name") or tag
        body = release.get("body") or ""
        assets = release.get("assets", [])

        log_func(f"处理 Release: {name} (tag: {tag})")

        if tag in existing_tags:
            log_func(f"Gitee 上已存在 tag {tag} 的 Release，跳过创建")
        else:
            commit_sha = None
            try:
                code, output = run_git(["rev-parse", tag], cwd=repo_git_dir)
                if code == 0:
                    commit_sha = output.strip()
                else:
                    log_func(f"无法获取 tag {tag} 的 commit SHA: {output}")
            except Exception as e:
                log_func(f"获取 commit SHA 异常: {e}")

            if commit_sha:
                gitee_release = create_gitee_release(
                    token, username, repo_name, tag, name, body, commit_sha, log_func
                )
                if gitee_release:
                    log_func(f"Release 创建成功: {name}")
                    existing_tags.add(tag)
            else:
                log_func("跳过该 Release 创建（缺少 target_commitish）")

        if assets:
            tag_dir = os.path.join(base_dir, tag)
            os.makedirs(tag_dir, exist_ok=True)
            log_func(f"下载附件到本地目录: {tag_dir}")
            for asset in assets:
                asset_name = asset.get("name", "unknown")
                download_url = asset.get("browser_download_url")
                if not download_url:
                    log_func(f"附件 {asset_name} 缺少下载链接，跳过")
                    continue

                local_path = os.path.join(tag_dir, asset_name)
                if os.path.exists(local_path):
                    log_func(f"附件 {asset_name} 已存在，跳过下载")
                    continue
                log_func(f"下载附件: {asset_name} ...")
                if download_file(download_url, local_path, log_func):
                    log_func(f"附件已保存: {local_path}")
                else:
                    log_func(f"附件 {asset_name} 下载失败")

    log_func("Releases 迁移处理完成")
    log_func(f"所有附件已保存到: {base_dir}")
    log_func("请手动登录 Gitee 网页，将对应文件上传到 Release 中")

def get_cache_dir(custom_dir=None):
    if custom_dir:
        cache_root = custom_dir
    else:
        cache_root = os.path.join(os.path.expanduser("~"), ".gitee_migrator_cache")
    os.makedirs(cache_root, exist_ok=True)
    return cache_root

def update_or_clone_mirror(github_url, cache_repo_path, log_func):
    if os.path.exists(cache_repo_path):
        log_func(f"检测到缓存仓库，更新中: {cache_repo_path}")
        code, output = run_git(["remote", "update", "--prune"], cwd=cache_repo_path)
        if code != 0:
            log_func(f"更新缓存失败，尝试重新克隆...")
            shutil.rmtree(cache_repo_path, ignore_errors=True)
            code, output = run_git(["clone", "--mirror", github_url, cache_repo_path])
            if code != 0:
                raise Exception(f"克隆失败:\n{output}")
            log_func("重新克隆完成")
        else:
            log_func("缓存更新完成")
    else:
        log_func("首次克隆仓库...")
        code, output = run_git(["clone", "--mirror", github_url, cache_repo_path])
        if code != 0:
            raise Exception(f"克隆失败:\n{output}")
        log_func("克隆完成")

def migrate_repo(github_url, token, repo_name, private, description, log_func, update_eta=None,
                 migrate_releases_flag=True, assets_base_dir=None, cache_dir=None,
                 force_mirror=False, sync_about=True):
    try:
        owner, repo = extract_github_owner_repo(github_url)
    except Exception:
        owner, repo = "unknown", repo_name

    cache_root = get_cache_dir(cache_dir)
    cache_repo_path = os.path.join(cache_root, f"{owner}__{repo}.git")

    t_start = time.time()
    try:
        update_or_clone_mirror(github_url, cache_repo_path, log_func)

        t_clone_done = time.time()
        clone_time = t_clone_done - t_start
        total_estimated = clone_time * 2
        eta = t_start + total_estimated
        eta_str = datetime.fromtimestamp(eta).strftime("%H:%M:%S")
        if update_eta:
            update_eta(f"预计完成时间：{eta_str}")

        log_func("获取 Gitee 用户信息...")
        username = get_gitee_username(token)
        log_func(f"当前 Gitee 用户: {username}")

        github_desc = ""
        github_homepage = ""
        if sync_about:
            try:
                github_desc, github_homepage = get_github_repo_info(owner, repo)
                log_func(f"GitHub 描述: {github_desc or '无'}, 主页: {github_homepage or '无'}")
            except Exception as e:
                log_func(f"获取 GitHub 简介失败: {e}")

        safe_username = quote(username, safe="")
        safe_token = quote(token, safe="")
        push_url = f"https://{safe_username}:{safe_token}@gitee.com/{safe_username}/{quote(repo_name, safe='')}.git"

        exists = check_repo_exists(token, username, repo_name)
        if exists:
            log_func("Gitee 上已存在同名仓库")
            is_new = False
        else:
            create_desc = description
            if sync_about and github_desc:
                create_desc = github_desc
            log_func("创建 Gitee 仓库...")
            repo_info = create_gitee_repo(token, repo_name, private, create_desc)
            log_func(f"仓库创建成功: {repo_info['full_name']}")
            is_new = True

        if force_mirror:
            log_func("开始强制镜像同步（将删除 Gitee 上多余内容并覆盖所有分支）...")
            code, output = run_git(["push", "--mirror", "--force", push_url], cwd=cache_repo_path)
            if code != 0:
                safe_output = output.replace(token, "***")
                raise Exception(f"强制镜像推送失败:\n{safe_output}")
            log_func("强制镜像推送完成")
        else:
            if is_new:
                log_func("推送到 Gitee（全量，所有分支和标签）...")
                code, output = run_git(["push", "--mirror", push_url], cwd=cache_repo_path)
                if code != 0:
                    safe_output = output.replace(token, "***")
                    raise Exception(f"推送失败:\n{safe_output}")
            else:
                log_func("推送所有分支（增量，不会删除远端分支）...")
                code, output = run_git(["push", "--all", push_url], cwd=cache_repo_path)
                if code != 0:
                    safe_output = output.replace(token, "***")
                    log_func(f"分支推送出现警告/错误（可能部分分支因非快进被拒绝）:\n{safe_output}")
                else:
                    log_func("分支推送完成")

                log_func("推送所有标签...")
                code, output = run_git(["push", "--tags", push_url], cwd=cache_repo_path)
                if code != 0:
                    safe_output = output.replace(token, "***")
                    log_func(f"标签推送出现警告/错误:\n{safe_output}")
                else:
                    log_func("标签推送完成")

        if sync_about:
            try:
                if github_desc or github_homepage:
                    update_gitee_repo_info(token, username, repo_name, github_desc, github_homepage, log_func)
                else:
                    log_func("GitHub 仓库没有描述或主页，跳过简介同步")
            except Exception as e:
                log_func(f"同步简介失败: {e}")

        if migrate_releases_flag:
            try:
                migrate_releases(github_url, token, repo_name, cache_repo_path, assets_base_dir, log_func)
            except Exception as e:
                log_func(f"迁移 Releases 失败: {e}")

        log_func("✅ 迁移完成！")
        if update_eta:
            update_eta("迁移已完成")
        return True
    finally:
        pass

class PlaceholderEntry(tk.Entry):
    def __init__(self, master=None, placeholder="", placeholder_color="gray", mask_char=None, **kwargs):
        super().__init__(master, **kwargs)
        self.placeholder = placeholder
        self.placeholder_color = placeholder_color
        self.default_fg = self.cget("fg")
        self.mask_char = mask_char
        self.bind("<FocusIn>", self._clear_placeholder)
        self.bind("<FocusOut>", self._show_placeholder)
        self._show_placeholder()

    def _clear_placeholder(self, event=None):
        if self.get() == self.placeholder:
            self.delete(0, tk.END)
            self.configure(fg=self.default_fg)
            if self.mask_char:
                self.configure(show=self.mask_char)

    def _show_placeholder(self, event=None):
        if self.get() == "":
            if self.mask_char:
                self.configure(show="")
            self.insert(0, self.placeholder)
            self.configure(fg=self.placeholder_color)

    def insert(self, index, string):
        if self.get() == self.placeholder:
            self.delete(0, tk.END)
            self.configure(fg=self.default_fg)
            if self.mask_char:
                self.configure(show=self.mask_char)
        super().insert(index, string)

    def get_value(self):
        if self.get() == self.placeholder:
            return ""
        return self.get()

def add_context_menu(widget):
    menu = tk.Menu(widget, tearoff=0)

    def clear_placeholder_if_needed():
        if hasattr(widget, 'placeholder') and widget.get() == widget.placeholder:
            widget._clear_placeholder()

    menu.add_command(label="剪切", command=lambda: widget.event_generate("<<Cut>>"))
    menu.add_command(label="复制", command=lambda: widget.event_generate("<<Copy>>"))
    menu.add_command(label="粘贴", command=lambda: (clear_placeholder_if_needed(), widget.event_generate("<<Paste>>")))
    menu.add_separator()
    menu.add_command(label="全选", command=lambda: widget.event_generate("<<SelectAll>>"))
    widget.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))
    widget.bind("<Button-2>", lambda e: menu.tk_popup(e.x_root, e.y_root))

class App:
    def __init__(self, root):
        self.root = root
        root.title("GitHub → Gitee 仓库迁移工具")
        root.geometry("560x650")
        # 禁用窗口调整大小（同时禁用最大化按钮）
        root.resizable(False, False)

        # 配置文件路径
        self.config_file = os.path.join(os.path.expanduser("~"), ".gitee_migrator_config.json")

        main_frame = ttk.Frame(root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Gitee 令牌
        ttk.Label(main_frame, text="Gitee 私人令牌:").grid(row=0, column=0, sticky=tk.W, pady=5)
        token_frame = ttk.Frame(main_frame)
        token_frame.grid(row=0, column=1, sticky=tk.EW, pady=5)
        self.token_entry = PlaceholderEntry(token_frame, width=40, placeholder="请输入你的Gitee秘钥", mask_char="*")
        self.token_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.token_visible = False
        self.toggle_token_btn = ttk.Button(token_frame, text="👁", width=3, command=self.toggle_token_visibility)
        self.toggle_token_btn.pack(side=tk.LEFT, padx=(5, 0))
        add_context_menu(self.token_entry)

        # GitHub 仓库地址
        ttk.Label(main_frame, text="GitHub 仓库地址:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.github_entry = PlaceholderEntry(main_frame, width=40, placeholder="https://github.com/username/repo.git")
        self.github_entry.grid(row=1, column=1, sticky=tk.EW, pady=5)
        add_context_menu(self.github_entry)

        # Gitee 仓库名
        ttk.Label(main_frame, text="Gitee 仓库名(可选):").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.repo_name_entry = PlaceholderEntry(main_frame, width=40, placeholder="留空自动从 URL 提取")
        self.repo_name_entry.grid(row=2, column=1, sticky=tk.EW, pady=5)
        add_context_menu(self.repo_name_entry)

        # 描述
        ttk.Label(main_frame, text="仓库描述(可选):").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.desc_entry = ttk.Entry(main_frame, width=40)
        self.desc_entry.grid(row=3, column=1, sticky=tk.EW, pady=5)
        add_context_menu(self.desc_entry)

        # 是否私有
        self.private_var = tk.BooleanVar(value=False)
        self.private_check = ttk.Checkbutton(main_frame, text="创建为私有仓库", variable=self.private_var)
        self.private_check.grid(row=4, column=1, sticky=tk.W, pady=5)

        # 是否迁移 Releases
        self.migrate_releases_var = tk.BooleanVar(value=True)
        self.migrate_releases_check = ttk.Checkbutton(main_frame, text="同时迁移发行版（Releases）", variable=self.migrate_releases_var)
        self.migrate_releases_check.grid(row=5, column=1, sticky=tk.W, pady=5)

        # 强制镜像同步
        self.force_mirror_var = tk.BooleanVar(value=False)
        self.force_mirror_check = ttk.Checkbutton(
            main_frame,
            text="强制镜像同步（将删除 Gitee 上多余内容）",
            variable=self.force_mirror_var
        )
        self.force_mirror_check.grid(row=6, column=1, sticky=tk.W, pady=5)

        # 同步仓库简介
        self.sync_about_var = tk.BooleanVar(value=True)
        self.sync_about_check = ttk.Checkbutton(
            main_frame,
            text="同步仓库简介（描述和主页）",
            variable=self.sync_about_var
        )
        self.sync_about_check.grid(row=7, column=1, sticky=tk.W, pady=5)

        # 附件保存目录
        ttk.Label(main_frame, text="附件保存根目录(可选):").grid(row=8, column=0, sticky=tk.W, pady=5)
        assets_frame = ttk.Frame(main_frame)
        assets_frame.grid(row=8, column=1, sticky=tk.EW, pady=5)
        self.assets_dir_entry = ttk.Entry(assets_frame, width=35)
        self.assets_dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.browse_assets_btn = ttk.Button(assets_frame, text="浏览", command=self.browse_assets_dir)
        self.browse_assets_btn.pack(side=tk.LEFT, padx=(5, 0))
        add_context_menu(self.assets_dir_entry)

        # 缓存目录
        ttk.Label(main_frame, text="缓存目录(可选):").grid(row=9, column=0, sticky=tk.W, pady=5)
        cache_frame = ttk.Frame(main_frame)
        cache_frame.grid(row=9, column=1, sticky=tk.EW, pady=5)
        self.cache_dir_entry = ttk.Entry(cache_frame, width=35)
        self.cache_dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.browse_cache_btn = ttk.Button(cache_frame, text="浏览", command=self.browse_cache_dir)
        self.browse_cache_btn.pack(side=tk.LEFT, padx=(5, 0))
        add_context_menu(self.cache_dir_entry)

        # 开始按钮
        self.start_btn = ttk.Button(main_frame, text="开始迁移", command=self.start_migration)
        self.start_btn.grid(row=10, column=0, columnspan=2, pady=10)

        # 预计完成时间标签
        self.eta_label = ttk.Label(main_frame, text="预计完成时间：--", foreground="blue")
        self.eta_label.grid(row=11, column=0, columnspan=2, pady=2)

        # 日志区域
        ttk.Label(main_frame, text="日志输出:").grid(row=12, column=0, sticky=tk.W, pady=5)
        self.log_text = scrolledtext.ScrolledText(main_frame, height=12, state=tk.DISABLED, wrap=tk.WORD)
        self.log_text.grid(row=13, column=0, columnspan=2, sticky=tk.EW + tk.NS, pady=5)
        add_context_menu(self.log_text)

        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(13, weight=1)

        # 加载配置
        self.load_config()

    def load_config(self):
        """从配置文件加载上次保存的目录"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                assets_dir = config.get("assets_dir", "")
                cache_dir = config.get("cache_dir", "")
                if assets_dir:
                    self.assets_dir_entry.delete(0, tk.END)
                    self.assets_dir_entry.insert(0, assets_dir)
                if cache_dir:
                    self.cache_dir_entry.delete(0, tk.END)
                    self.cache_dir_entry.insert(0, cache_dir)
        except Exception:
            pass

    def save_config(self):
        """保存当前目录配置到文件"""
        try:
            config = {
                "assets_dir": self.assets_dir_entry.get().strip(),
                "cache_dir": self.cache_dir_entry.get().strip(),
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def browse_assets_dir(self):
        selected_dir = filedialog.askdirectory(title="选择附件保存根目录")
        if selected_dir:
            self.assets_dir_entry.delete(0, tk.END)
            self.assets_dir_entry.insert(0, selected_dir)
            self.save_config()

    def browse_cache_dir(self):
        selected_dir = filedialog.askdirectory(title="选择缓存目录")
        if selected_dir:
            self.cache_dir_entry.delete(0, tk.END)
            self.cache_dir_entry.insert(0, selected_dir)
            self.save_config()

    def toggle_token_visibility(self):
        if self.token_entry.get_value() == "":
            return
        self.token_visible = not self.token_visible
        if self.token_visible:
            self.token_entry.config(show="")
            self.toggle_token_btn.config(text="🙈")
        else:
            self.token_entry.config(show=self.token_entry.mask_char)
            self.toggle_token_btn.config(text="👁")

    def update_eta(self, text):
        self.root.after(0, lambda: self.eta_label.config(text=text))

    def log(self, msg):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)
        self.root.update_idletasks()

    def start_migration(self):
        # 保存当前配置
        self.save_config()

        token = self.token_entry.get_value().strip()
        github_url = self.github_entry.get_value().strip()
        repo_name = self.repo_name_entry.get_value().strip()
        description = self.desc_entry.get().strip()
        private = self.private_var.get()
        migrate_releases_flag = self.migrate_releases_var.get()
        force_mirror = self.force_mirror_var.get()
        sync_about = self.sync_about_var.get()
        assets_base_dir = self.assets_dir_entry.get().strip()
        cache_dir = self.cache_dir_entry.get().strip()

        if not token:
            messagebox.showerror("错误", "请输入 Gitee 私人令牌")
            return
        if not github_url:
            messagebox.showerror("错误", "请输入 GitHub 仓库地址")
            return

        if not repo_name:
            try:
                repo_name = extract_repo_name(github_url)
            except Exception as e:
                messagebox.showerror("错误", str(e))
                return

        self.start_btn.configure(state=tk.DISABLED)
        self.eta_label.config(text="预计完成时间：计算中...")
        self.log("=" * 50)
        self.log(f"开始迁移: {github_url} -> Gitee:{repo_name}")
        if force_mirror:
            self.log("同步模式：强制镜像（会删除 Gitee 上多余内容）")
        else:
            self.log("同步模式：增量同步（不删除 Gitee 内容）")
        if sync_about:
            self.log("将同步仓库简介（描述和主页）")
        if migrate_releases_flag:
            self.log("将同时迁移 Releases（发行版）")
            if assets_base_dir:
                self.log(f"附件保存根目录: {assets_base_dir}")
            else:
                self.log("附件保存根目录: 默认（用户主目录/gitee_release_assets）")
        if cache_dir:
            self.log(f"缓存目录: {cache_dir}")
        else:
            self.log("缓存目录: 默认（用户主目录/.gitee_migrator_cache）")

        def task():
            try:
                migrate_repo(
                    github_url,
                    token,
                    repo_name,
                    private,
                    description,
                    self.log,
                    self.update_eta,
                    migrate_releases_flag,
                    assets_base_dir,
                    cache_dir,
                    force_mirror,
                    sync_about
                )
            except Exception as e:
                self.log(f"❌ 迁移失败: {e}")
                self.update_eta("迁移失败")
                messagebox.showerror("失败", str(e))
            finally:
                self.start_btn.configure(state=tk.NORMAL)

        threading.Thread(target=task, daemon=True).start()

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()