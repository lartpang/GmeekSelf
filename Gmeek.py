# -*- coding: utf-8 -*-
import argparse
import copy
import json
import math
import os
import re
import shutil
import time
import urllib
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

import requests
from feedgen.feed import FeedGenerator
from github import Github
from github.Issue import Issue
from github.Repository import Repository
from jinja2 import Environment, FileSystemLoader
from transliterate import translit
from xpinyin import Pinyin

from constant import I18N, ICONS, NEWLINE_CHAR


class GMEEK:
    def __init__(self, github_token, repo_name, issue_number):
        self.github_token = github_token
        self.repo_name = repo_name
        self.issue_number = issue_number

        self.root_dir = "docs/"
        self.post_folder = "post/"
        self.backup_dir = "backup/"
        self.post_dir = self.root_dir + self.post_folder
        self.old_feed_string = ""

        self.repo = self.get_repo(token=github_token, repo=self.repo_name)
        self.label_color_info = {l.name: "#" + l.color for l in self.repo.get_labels()}
        print(self.label_color_info)

        self.initialize_config()

    def initialize_config(self):
        self.blogBase = {
            "sub_page_labels": [],  # For the single page with a unique label. e.g. "about, link"
            "startSite": "",
            "filingNum": "",
            "max_posts_per_page": 15,
            "commentLabelColor": "#006b75",
            "yearColors": ["#bc4c00", "#0969da", "#1f883d", "#A333D0"],
            "i18n": "CN",
            "themeMode": "manual",
            "dayTheme": "light",
            "nightTheme": "dark",
            "urlMode": "pinyin",
            "script": "",
            "style": "",
            "bottomText": "",
            "showPostSource": 1,
            "iconList": {},
            "UTC": +8,
            "rssSplit": "sentence",
            "exlink": {},
            # should not be overrode
            "posts": OrderedDict(),  # 文章post页面信息 postListJson
            "sub_pages": OrderedDict(),  # 独立网页页面信息 singeListJson
            "label_color_info": self.label_color_info,
        }

        # 加载用户自定义的html格式的脚本和样式
        with open("config.json", "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        if user_cfg["script"].endswith(".html"):
            with open(user_cfg["script"], "r", encoding="UTF-8") as f:
                user_cfg["script"] = f.read() + NEWLINE_CHAR
        if user_cfg["style"].endswith(".html"):
            with open(user_cfg["style"], "r", encoding="UTF-8") as f:
                user_cfg["style"] = f.read() + NEWLINE_CHAR

        self.blogBase.update(user_cfg)
        self.blogBase.setdefault("displayTitle", self.blogBase["title"])
        self.blogBase.setdefault("faviconUrl", self.blogBase["avatarUrl"])
        self.blogBase.setdefault("ogImage", self.blogBase["avatarUrl"])

        if "homeUrl" not in self.blogBase:
            user_github_io = f"{self.repo.owner.login}.github.io"

            self.blogBase["homeUrl"] = f"https://{user_github_io}"
            if f"{self.repo.name}".lower() != user_github_io.lower():
                # 非user.github.io仓库
                self.blogBase["homeUrl"] += f"/{self.repo.name}"
        print("GitHub Pages URL: ", self.blogBase["homeUrl"])

        self.i18n = I18N.get(self.blogBase["i18n"], "EN")
        self.TZ = timezone(timedelta(hours=self.blogBase["UTC"]))

    @staticmethod
    def get_repo(token: str, repo: str) -> Repository:
        return Github(login_or_token=token).get_repo(repo)

    @staticmethod
    def generate_post_description(issueBody: str = None):
        """Generate the post description corresponding to the issue.
        Due to the complexity of the post description, it is not implemented yet.

        Args:
            issueBody (str, optional): Issue body. Defaults to None.
        """
        postDescription = ""
        return postDescription

    def render_html(self, template, blogBase, icon, html, posts=None):
        file_loader = FileSystemLoader("templates")
        env = Environment(loader=file_loader)
        template = env.get_template(template)

        posts = posts or {}
        output = template.render(blogBase=blogBase, posts=posts, i18n=self.i18n, IconList=icon)
        with open(html, "w", encoding="UTF-8") as f:
            f.write(output)
        print(f"create {html} with template {template}")

    def markdown2html(self, mdstr: str):
        payload = {"text": mdstr, "mode": "gfm"}
        headers = {"Authorization": "token {}".format(self.github_token)}
        try:
            response = requests.post(
                "https://api.github.com/markdown", json=payload, headers=headers
            )
            response.raise_for_status()  # Raises an exception if status code is not 200
            return response.text
        except requests.RequestException as e:
            raise Exception("markdown2html error: {}".format(e))

    def create_post_html(self, post_cfg: dict):
        with open(post_cfg["md_path"], "r", encoding="UTF-8") as f:
            post_body = self.markdown2html(f.read())

        # Import mathjax for supporting the math formulas
        if "<math-renderer" in post_body:
            post_body = re.sub(r"<math-renderer.*?>", "", post_body)
            post_body = re.sub(r"</math-renderer>", "", post_body)
            post_cfg["script"] += "".join(
                [
                    '<script>MathJax = {tex: {inlineMath: [["$", "$"]]}};</script>',
                    '<script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>',
                ]
            )

        post_info = copy.deepcopy(self.blogBase)
        post_info["postTitle"] = post_cfg["postTitle"]
        post_info["postUrl"] = self.blogBase["homeUrl"] + "/" + post_cfg["postUrl"]
        post_info["description"] = post_cfg["description"]
        post_info["ogImage"] = post_cfg["ogImage"]
        post_info["postBody"] = post_body
        post_info["commentNum"] = post_cfg["commentNum"]
        post_info["style"] = post_cfg["style"]
        post_info["script"] = post_cfg["script"]
        post_info["top"] = post_cfg["top"]
        post_info["postSourceUrl"] = post_cfg["postSourceUrl"]
        post_info["repoName"] = self.repo_name
        post_info["highlight"] = int("highlight" in post_body)

        if post_cfg["labels"][0] in self.blogBase["sub_page_labels"]:
            post_info["bottomText"] = ""

        post_icons = {k: ICONS[k] for k in ["sun", "moon", "sync", "home", "github"]}
        self.render_html("post.html", post_info, post_icons, post_cfg["htmlDir"])
        print(f'created post html {post_cfg["htmlDir"]} from {post_cfg["postTitle"]}')

    def create_post_index_html(self):
        index_icons = {
            k: ICONS[k]
            for k in ["sun", "moon", "sync", "search", "rss", "upload", "post"]
            + self.blogBase["sub_page_labels"]
        }
        index_icons.update(self.blogBase["iconList"])

        # all_post_infos = list(self.blogBase["posts"].items())
        all_post_infos = sorted(
            self.blogBase["posts"].items(),
            key=lambda x: (x[1]["top"], x[1]["createdAt"]),
            reverse=True,
        )
        max_posts_per_page = self.blogBase["max_posts_per_page"]
        num_pages = math.ceil(len(all_post_infos) / max_posts_per_page)
        for page_idx in range(num_pages):
            start_idx = page_idx * max_posts_per_page
            end_idx = (page_idx + 1) * max_posts_per_page
            curr_posts = OrderedDict(all_post_infos[start_idx:end_idx])
            print(f"Post Range={(start_idx, end_idx)} Number of Posts:{len(curr_posts)}")

            if page_idx == 0:
                # the total number of posts is less than max_posts_per_page
                post_html = self.root_dir + "index.html"
                self.blogBase["prevUrl"] = "disabled"
                if page_idx + 1 < num_pages:  # there is a next page
                    self.blogBase["nextUrl"] = "/page1.html"
                else:  # current page is the last page with a full list
                    self.blogBase["nextUrl"] = "disabled"
            else:
                post_html = self.root_dir + f"page{page_idx}.html"
                if page_idx == 1:
                    self.blogBase["prevUrl"] = "/index.html"
                else:
                    self.blogBase["prevUrl"] = f"/page{page_idx-1}.html"
                if page_idx + 1 < num_pages:  # there is a next page
                    self.blogBase["nextUrl"] = f"/page{page_idx+1}.html"
                else:  # current page is the last page with a full list
                    self.blogBase["nextUrl"] = "disabled"
            self.render_html("plist.html", self.blogBase, index_icons, post_html, curr_posts)

        # create tag page
        tag_icons = {k: ICONS[k] for k in ["sun", "moon", "sync", "home", "search", "post"]}
        tag_html = self.root_dir + "tag.html"
        self.render_html("tag.html", self.blogBase, tag_icons, tag_html, curr_posts)

    def create_feed_xml(self):
        feed = FeedGenerator()
        feed.title(self.blogBase["title"])
        feed.description(self.blogBase["subTitle"])
        feed.link(href=self.blogBase["homeUrl"])
        feed.image(url=self.blogBase["avatarUrl"], title="avatar", link=self.blogBase["homeUrl"])
        feed.copyright(self.blogBase["title"])
        feed.managingEditor(self.blogBase["title"])
        feed.webMaster(self.blogBase["title"])
        feed.ttl("60")

        for num in self.blogBase["sub_pages"]:
            item = feed.add_item()
            item.guid(
                self.blogBase["homeUrl"] + "/" + self.blogBase["sub_pages"][num]["postUrl"],
                permalink=True,
            )
            item.title(self.blogBase["sub_pages"][num]["postTitle"])
            item.description(self.blogBase["sub_pages"][num]["description"])
            item.link(
                href=self.blogBase["homeUrl"] + "/" + self.blogBase["sub_pages"][num]["postUrl"]
            )
            item.pubDate(
                time.strftime(
                    "%a, %d %b %Y %H:%M:%S +0000",
                    time.gmtime(self.blogBase["sub_pages"][num]["createdAt"]),
                )
            )

        for post_info in sorted(
            self.blogBase["posts"].values(), key=lambda x: x["createdAt"], reverse=False
        ):
            item = feed.add_item()
            item.guid(self.blogBase["homeUrl"] + "/" + post_info["postUrl"], permalink=True)
            item.title(post_info["postTitle"])
            item.description(post_info["description"])
            item.link(href=self.blogBase["homeUrl"] + "/" + post_info["postUrl"])
            item.pubDate(
                time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime(post_info["createdAt"]))
            )

        if self.old_feed_string != "":
            feed.rss_file(self.root_dir + "new.xml")
            with open(self.root_dir + "new.xml", "r", encoding="utf-8") as f:
                new = f.read()

            new = re.sub(r"<lastBuildDate>.*?</lastBuildDate>", "", new)
            old = re.sub(r"<lastBuildDate>.*?</lastBuildDate>", "", self.old_feed_string)
            os.remove(self.root_dir + "new.xml")

            if new == old:
                print("====== rss xml no update ======")
                with open(self.root_dir + "rss.xml", "w") as f:
                    f.write(self.old_feed_string)
                return

        print("====== create rss xml ======")
        feed.rss_file(self.root_dir + "rss.xml")

    def create_file_name(self, issue: Issue, useLabel: bool = False):
        if useLabel:
            fileName = issue.labels[0].name
        else:
            if self.blogBase["urlMode"] == "issue":
                fileName = str(issue.number)
            elif self.blogBase["urlMode"] == "ru_translit":
                fileName = translit(issue.title, language_code="ru", reversed=True)
                fileName = str(fileName).replace(" ", "-")
            else:
                fileName = Pinyin().get_pinyin(issue.title)
        return re.sub(r"[<>:/\\|?*\"]|[\0-\31]", "-", fileName)

    def update_post_info(self, issue: Issue):
        """Update the posts and sub_pages based on the issue information.

        Args:
            issue (Issue): issue object.

        Returns:
            str: "sub_pages" or "posts".
        """
        if len(issue.labels) < 1:
            return

        # TODO: 这里只考虑了标签列表中的第一个标签
        if issue.labels[0].name in self.blogBase["sub_page_labels"]:
            post_type = "sub_pages"
            html_name = self.create_file_name(issue, useLabel=True)
            html_path = self.root_dir + f"{html_name}.html"
        else:
            post_type = "posts"
            html_name = self.create_file_name(issue, useLabel=False)
            html_path = self.post_dir + f"{html_name}.html"

        post_cfg = {}
        post_cfg["htmlDir"] = html_path
        post_cfg["labels"] = [label.name for label in issue.labels]
        # post_cfg["labelColor"]=self.label_color_info[issue.labels[0].name]
        post_cfg["postTitle"] = issue.title
        post_cfg["postUrl"] = urllib.parse.quote(html_path[len(self.root_dir) :])
        post_cfg["postSourceUrl"] = (
            "https://github.com/" + self.repo_name + "/issues/" + str(issue.number)
        )
        post_cfg["commentNum"] = issue.get_comments().totalCount

        post_cfg["top"] = 0
        for event in issue.get_events():
            if event.event == "pinned":
                post_cfg["top"] = 1
            # elif event.event == "unpinned":
            #     post_cfg["top"] = 0

        post_cfg["num_words"] = len(issue.body)
        post_cfg["description"] = self.generate_post_description(issue.body)

        # Parse and import the customized settings from the specific comment of the post body
        # format: <!-- myconfig:{key1:value1,key2:value2,...} -->
        print("Parse and import customized settings...")
        post_cfg = {}
        for cfg in re.findall(r"<!--\s*myconfig:{([^}]*?)}\s*-->", issue.body, flags=re.MULTILINE):
            post_cfg.update(json.loads(cfg))
        print("Customized settings: ", post_cfg)

        post_cfg["createdAt"] = post_cfg.get(
            "timestamp", int(time.mktime(issue.created_at.timetuple()))
        )
        post_cfg["style"] = self.blogBase["style"] + post_cfg.get("style", "")
        post_cfg["script"] = self.blogBase["script"] + post_cfg.get("script", "")
        post_cfg["ogImage"] = post_cfg.get("ogImage", self.blogBase["ogImage"])

        thisTime = datetime.fromtimestamp(post_cfg["createdAt"]).astimezone(self.TZ)
        thisYear = thisTime.year
        post_cfg["createdDate"] = thisTime.strftime("%Y-%m-%d")
        post_cfg["dateLabelColor"] = self.blogBase["yearColors"][
            int(thisYear) % len(self.blogBase["yearColors"])
        ]

        md_name = re.sub(r"[<>:/\\|?*\"]|[\0-\31]", "-", issue.title)
        md_path = self.backup_dir + md_name + ".md"
        post_cfg["md_path"] = md_path
        if issue.body is not None:
            with open(md_path, "w", encoding="UTF-8") as f:
                f.write(issue.body)

        # self.blogBase[post_type][f"P{issue.number}"] = post_cfg
        return post_type, post_cfg

    def update_all_posts(self):
        """Remove all old files and rebuild all html"""
        print("====== start create static html ======")

        workspace_path = os.environ.get("GITHUB_WORKSPACE")
        if os.path.exists(workspace_path + "/" + self.backup_dir):
            shutil.rmtree(workspace_path + "/" + self.backup_dir)
        if os.path.exists(workspace_path + "/" + self.root_dir):
            shutil.rmtree(workspace_path + "/" + self.root_dir)
        if os.path.exists(self.backup_dir):
            shutil.rmtree(self.backup_dir)
        if os.path.exists(self.root_dir):
            shutil.rmtree(self.root_dir)
        os.mkdir(self.backup_dir)
        os.mkdir(self.root_dir)
        os.mkdir(self.post_dir)

        # Only use the open issues
        for issue in self.repo.get_issues(state="open"):
            post_type, post_cfg = self.update_post_info(issue)
            self.blogBase[post_type][f"P{issue.number}"] = post_cfg
            self.create_post_html(post_cfg)

        self.create_post_index_html()
        self.create_feed_xml()
        print("====== create static html end ======")

    def update_single_post(self, number: str):
        print("====== start create static html ======")

        issue = self.repo.get_issue(int(number))
        post_type, post_cfg = self.update_post_info(issue)
        self.blogBase[post_type][f"P{number}"] = post_cfg
        self.create_post_html(post_cfg)

        self.create_post_index_html()
        self.create_feed_xml()
        print("====== create static html end ======")

    def update_blog_base(self):
        if not os.path.exists("blogBase.json"):
            print("blogBase is not exists, run_all")
            self.update_all_posts()
        else:
            if os.path.exists(self.root_dir + "rss.xml"):
                with open(self.root_dir + "rss.xml", "r", encoding="utf-8") as f:
                    self.old_feed_string = f.read()

            if self.issue_number == "0" or self.issue_number == "":
                print(f"issue_number=={self.issue_number}, run_all")
                self.update_all_posts()
            else:
                print("blogBase is exists and issue_number!=0, run_one")
                with open("blogBase.json", "r") as f:
                    old_blog_base = json.load(f)

                for key, value in old_blog_base.items():
                    self.blogBase[key] = value

                self.update_single_post(self.issue_number)

        with open("blogBase.json", "w") as f:
            json.dump(self.blogBase, f, indent=2)

    def update_post_list_json(self):
        print("====== create postList.json file ======")

        sorted_post_infos = OrderedDict(
            sorted(self.blogBase["posts"].items(), key=lambda x: x[1]["createdAt"], reverse=True)
        )

        num_comments = 0
        num_words = 0
        useless_keys = [
            "description",
            "postSourceUrl",
            "htmlDir",
            "createdAt",
            "script",
            "style",
            "top",
            "ogImage",
        ]
        for i in sorted_post_infos:
            for k in useless_keys:
                if k in sorted_post_infos[i]:
                    del sorted_post_infos[i][k]

            if "commentNum" in sorted_post_infos[i]:
                num_comments = num_comments + sorted_post_infos[i]["commentNum"]
                del sorted_post_infos[i]["commentNum"]

            if "num_words" in sorted_post_infos[i]:
                num_words = num_words + sorted_post_infos[i]["num_words"]
                del sorted_post_infos[i]["num_words"]

        sorted_post_infos["label_color_info"] = self.label_color_info

        with open(self.root_dir + "postList.json", "w") as f:
            json.dump(sorted_post_infos, f, indent=2)
        return num_comments, num_words

    def update_readme_md(self, num_comments, num_words):
        print("====== update readme file ======")
        workspace_path = os.environ.get("GITHUB_WORKSPACE")

        readme = NEWLINE_CHAR.join(
            [
                f'# {self.blogBase["title"]} :link: {self.blogBase["homeUrl"]}',
                "This is a simple static self based on GitHub Issue and Page.",
                "| :alarm_clock: Late updated                            | :page_facing_up: Articles                                                | :speech_balloon: Comments | :hibiscus: Words |",
                "| ----------------------------------------------------- | ------------------------------------------------------------------------ | ------------------------- | ---------------- |",
                f"|{datetime.now(self.TZ).strftime("%Y-%m-%d %H:%M:%S")} | [{len(self.blogBase["posts"]) - 1}]({self.blogBase["homeUrl"]}/tag.html) | {num_comments}            | {num_words}      |",
                "---",
                "*Powered by [GmeekSelf](https://github.com/lartpang/GmeekSelf) modified from [Gmeek](https://github.com/Meekdai/Gmeek)*",
            ]
        )
        with open(workspace_path + "/README.md", "w") as f:
            f.write(readme)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("github_token", help="github_token")
    parser.add_argument("repo_name", help="repo_name")
    parser.add_argument("--issue_number", help="issue_number", default=0, required=False)
    args = parser.parse_args()

    blog = GMEEK(args.github_token, args.repo_name, args.issue_number)
    blog.update_blog_base()
    num_comments, num_words = blog.update_post_list_json(blog)
    if os.environ.get("GITHUB_EVENT_NAME") != "schedule":
        blog.update_readme_md(num_comments, num_words)


if __name__ == "__main__":
    main()
