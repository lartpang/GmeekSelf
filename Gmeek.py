# -*- coding: utf-8 -*-
import argparse
import copy
import datetime
import json
import math
import os
import re
import shutil
import time
import urllib
from collections import OrderedDict

import requests
from feedgen.feed import FeedGenerator
from github import Github
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

        self.repo = self.get_repo(self.repo_name)
        self.oldFeedString = ""

        self.labelColorInfo = {l.name: "#" + l.color for l in self.repo.get_labels()}
        print(self.labelColorInfo)

        self.defaultConfig()

    def get_repo(self, repo: str):
        user = Github(self.github_token)
        return user.get_repo(repo)

    def defaultConfig(self):
        self.blogBase = {
            "subPageList": [],
            "startSite": "",
            "filingNum": "",
            "maxNumOfPostPerPage": 15,
            "commentLabelColor": "#006b75",
            "yearColorList": ["#bc4c00", "#0969da", "#1f883d", "#A333D0"],
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
        }

        with open("config.json", "r", encoding="utf-8") as f:
            user_cfg = json.loads(f)

        # 加载用户自定义的html格式的脚本和样式
        if user_cfg["script"].endswith(".html"):
            with open(user_cfg["script"], "r", encoding="UTF-8") as f:
                user_cfg["script"] = f.read() + NEWLINE_CHAR
        if user_cfg["style"].endswith(".html"):
            with open(user_cfg["style"], "r", encoding="UTF-8") as f:
                user_cfg["style"] = f.read() + NEWLINE_CHAR

        self.blogBase.update(user_cfg)
        self.blogBase["allPostInfo"] = OrderedDict()  # 文章post页面信息
        self.blogBase["subPageInfo"] = OrderedDict()  # 独立网页页面信息
        self.blogBase["labelColorInfo"] = self.labelColorInfo
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
        self.TZ = datetime.timezone(datetime.timedelta(hours=self.blogBase["UTC"]))

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

    def renderHtml(self, template, blogBase, allPostInfo, html, icon):
        file_loader = FileSystemLoader("templates")
        env = Environment(loader=file_loader)
        template = env.get_template(template)
        output = template.render(
            blogBase=blogBase, allPostInfo=allPostInfo, i18n=self.i18n, IconList=icon
        )
        with open(html, "w", encoding="UTF-8") as f:
            f.write(output)
        print(f"create {html} with template {template}")

    def createPostHtml(self, issue):
        mdFileName = re.sub(r"[<>:/\\|?*\"]|[\0-\31]", "-", issue["postTitle"])
        with open(self.backup_dir + mdFileName + ".md", "r", encoding="UTF-8") as f:
            post_body = self.markdown2html(f.read())

        if "<math-renderer" in post_body:
            post_body = re.sub(r"<math-renderer.*?>", "", post_body)
            post_body = re.sub(r"</math-renderer>", "", post_body)
            issue["script"] += "".join(
                [
                    '<script>MathJax = {tex: {inlineMath: [["$", "$"]]}};</script>',
                    '<script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>',
                ]
            )

        postBase = copy.deepcopy(self.blogBase)
        postBase["postTitle"] = issue["postTitle"]
        postBase["postUrl"] = self.blogBase["homeUrl"] + "/" + issue["postUrl"]
        postBase["description"] = issue["description"]
        postBase["ogImage"] = issue["ogImage"]
        postBase["postBody"] = post_body
        postBase["commentNum"] = issue["commentNum"]
        postBase["style"] = issue["style"]
        postBase["script"] = issue["script"]
        postBase["top"] = issue["top"]
        postBase["postSourceUrl"] = issue["postSourceUrl"]
        postBase["repoName"] = self.repo_name
        postBase["highlight"] = int("highlight" in post_body)

        if issue["labels"][0] in self.blogBase["subPageList"]:
            postBase["bottomText"] = ""

        postIcon = {k: ICONS[k] for k in ["sun", "moon", "sync", "home", "github"]}
        self.renderHtml("post.html", postBase, {}, issue["htmlDir"], postIcon)

        print(f'created postPage title={issue["postTitle"]} file={issue["htmlDir"]}')

    def createPlistHtml(self):
        # 由时间排序列表
        self.blogBase["allPostInfo"] = dict(
            sorted(
                self.blogBase["allPostInfo"].items(),
                key=lambda x: (x[1]["top"], x[1]["createdAt"]),
                reverse=True,
            )
        )

        plistIcon = {
            k: ICONS[k]
            for k in ["sun", "moon", "sync", "search", "rss", "upload", "post"]
            + self.blogBase["subPageList"]
        }
        plistIcon.update(self.blogBase["iconList"])

        tagIcon = {k: ICONS[k] for k in ["sun", "moon", "sync", "home", "search", "post"]}

        allPostInfoList = list(self.blogBase["allPostInfo"].items())
        numSparePosts = len(allPostInfoList)
        pageIndex = 0
        while True:
            topNum = pageIndex * self.blogBase["maxNumOfPostPerPage"]
            print(f"topNum={topNum} numSparePosts={numSparePosts}")

            if numSparePosts <= self.blogBase["maxNumOfPostPerPage"]:
                if pageIndex == 0:
                    # the total number of posts is less than maxNumOfPostPerPage
                    postsThisPage = dict(allPostInfoList[:numSparePosts])
                    htmlDir = self.root_dir + "index.html"

                    self.blogBase["prevUrl"] = "disabled"
                    self.blogBase["nextUrl"] = "disabled"
                else:  # the last page contains the rest of posts
                    # the total number of posts is more than maxNumOfPostPerPage
                    postsThisPage = dict(allPostInfoList[topNum:])
                    htmlDir = self.root_dir + f"page{pageIndex+1}.html"

                    if pageIndex == 1:
                        self.blogBase["prevUrl"] = "/index.html"
                    else:
                        self.blogBase["prevUrl"] = f"/page{pageIndex}.html"
                    self.blogBase["nextUrl"] = "disabled"

                self.renderHtml("plist.html", self.blogBase, postsThisPage, htmlDir, plistIcon)
                print("create " + htmlDir)
                break
            else:
                if pageIndex == 0:
                    # the total number of posts is more than maxNumOfPostPerPage
                    htmlDir = self.root_dir + "index.html"

                    self.blogBase["prevUrl"] = "disabled"
                    self.blogBase["nextUrl"] = "/page2.html"
                else:
                    htmlDir = self.root_dir + f"page{pageIndex+1}.html"

                    if pageIndex == 1:
                        self.blogBase["prevUrl"] = "/index.html"
                    else:
                        self.blogBase["prevUrl"] = f"/page{pageIndex}.html"
                    self.blogBase["nextUrl"] = f"/page{pageIndex+2}.html"

                numSparePosts -= self.blogBase["maxNumOfPostPerPage"]
                postsThisPage = dict(
                    allPostInfoList[topNum : topNum + self.blogBase["maxNumOfPostPerPage"]]
                )
                self.renderHtml("plist.html", self.blogBase, postsThisPage, htmlDir, plistIcon)
                print("create " + htmlDir)
            pageIndex += 1

        self.renderHtml(
            "tag.html", self.blogBase, postsThisPage, self.root_dir + "tag.html", tagIcon
        )
        print("create tag.html")

    def createPostlistHtml(self):
        # 由时间排序列表
        self.blogBase["allPostInfo"] = OrderedDict(
            sorted(
                self.blogBase["allPostInfo"].items(),
                key=lambda x: (x[1]["top"], x[1]["createdAt"]),
                reverse=True,
            )
        )

        plistIcon = {
            k: ICONS[k]
            for k in ["sun", "moon", "sync", "search", "rss", "upload", "post"]
            + self.blogBase["subPageList"]
        }
        plistIcon.update(self.blogBase["iconList"])

        tagIcon = {k: ICONS[k] for k in ["sun", "moon", "sync", "home", "search", "post"]}

        allPostInfoList = list(self.blogBase["allPostInfo"].items())
        maxNumOfPostPerPage = self.blogBase["maxNumOfPostPerPage"]
        numSparePosts = len(allPostInfoList)

        numPages = math.ceil(numSparePosts / maxNumOfPostPerPage)
        for pageIndex in range(numPages):
            startIndex = pageIndex * maxNumOfPostPerPage
            endIndex = (pageIndex + 1) * maxNumOfPostPerPage
            postsThisPage = dict(allPostInfoList[startIndex, endIndex])
            print(f"PostIndex={(startIndex, endIndex)} currNumPosts={len(postsThisPage)}")

            if pageIndex == 0:
                # the total number of posts is less than maxNumOfPostPerPage
                currHtml = self.root_dir + "index.html"

                self.blogBase["prevUrl"] = "disabled"
                if pageIndex + 1 < numPages:  # there is a next page
                    self.blogBase["nextUrl"] = "/page2.html"
                else:  # current page is the last page with a full list
                    self.blogBase["nextUrl"] = "disabled"
            else:
                currHtml = self.root_dir + f"page{pageIndex}.html"

                if pageIndex == 1:
                    self.blogBase["prevUrl"] = "/index.html"
                else:
                    self.blogBase["prevUrl"] = f"/page{pageIndex-1}.html"

                if pageIndex + 1 < numPages:  # there is a next page
                    self.blogBase["nextUrl"] = f"/page{pageIndex+1}.html"
                else:  # current page is the last page with a full list
                    self.blogBase["nextUrl"] = "disabled"

            self.renderHtml("plist.html", self.blogBase, postsThisPage, currHtml, plistIcon)

        tagHtml = self.root_dir + "tag.html"
        self.renderHtml("tag.html", self.blogBase, postsThisPage, tagHtml, tagIcon)

    def createFeedXml(self):
        self.blogBase["allPostInfo"] = OrderedDict(
            sorted(
                self.blogBase["allPostInfo"].items(),
                key=lambda x: x[1]["createdAt"],
                reverse=False,
            )
        )

        feed = FeedGenerator()
        feed.title(self.blogBase["title"])
        feed.description(self.blogBase["subTitle"])
        feed.link(href=self.blogBase["homeUrl"])
        feed.image(url=self.blogBase["avatarUrl"], title="avatar", link=self.blogBase["homeUrl"])
        feed.copyright(self.blogBase["title"])
        feed.managingEditor(self.blogBase["title"])
        feed.webMaster(self.blogBase["title"])
        feed.ttl("60")

        for num in self.blogBase["subPageInfo"]:
            item = feed.add_item()
            item.guid(
                self.blogBase["homeUrl"] + "/" + self.blogBase["subPageInfo"][num]["postUrl"],
                permalink=True,
            )
            item.title(self.blogBase["subPageInfo"][num]["postTitle"])
            item.description(self.blogBase["subPageInfo"][num]["description"])
            item.link(
                href=self.blogBase["homeUrl"] + "/" + self.blogBase["subPageInfo"][num]["postUrl"]
            )
            item.pubDate(
                time.strftime(
                    "%a, %d %b %Y %H:%M:%S +0000",
                    time.gmtime(self.blogBase["subPageInfo"][num]["createdAt"]),
                )
            )

        for num in self.blogBase["allPostInfo"]:
            item = feed.add_item()
            item.guid(
                self.blogBase["homeUrl"] + "/" + self.blogBase["allPostInfo"][num]["postUrl"],
                permalink=True,
            )
            item.title(self.blogBase["allPostInfo"][num]["postTitle"])
            item.description(self.blogBase["allPostInfo"][num]["description"])
            item.link(
                href=self.blogBase["homeUrl"] + "/" + self.blogBase["allPostInfo"][num]["postUrl"]
            )
            item.pubDate(
                time.strftime(
                    "%a, %d %b %Y %H:%M:%S +0000",
                    time.gmtime(self.blogBase["allPostInfo"][num]["createdAt"]),
                )
            )

        if self.oldFeedString != "":
            feed.rss_file(self.root_dir + "new.xml")
            with open(self.root_dir + "new.xml", "r", encoding="utf-8") as f:
                new = f.read()

            new = re.sub(r"<lastBuildDate>.*?</lastBuildDate>", "", new)
            old = re.sub(r"<lastBuildDate>.*?</lastBuildDate>", "", self.oldFeedString)
            os.remove(self.root_dir + "new.xml")

            if new == old:
                print("====== rss xml no update ======")
                with open(self.root_dir + "rss.xml", "w") as f:
                    f.write(self.oldFeedString)
                return

        print("====== create rss xml ======")
        feed.rss_file(self.root_dir + "rss.xml")

    def createFileName(self, issue, useLabel: bool = False):
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

    def addOnePostJson(self, issue):
        if len(issue.labels) < 1:
            return

        if issue.labels[0].name in self.blogBase["subPageList"]:
            listJsonName = "subPageInfo"
            htmlFile = self.createFileName(issue, useLabel=True)
            gen_Html = self.root_dir + f"{htmlFile}.html"
        else:
            listJsonName = "allPostInfo"
            htmlFile = self.createFileName(issue, useLabel=False)
            gen_Html = self.post_dir + f"{htmlFile}.html"

        postNum = "P" + str(issue.number)
        self.blogBase[listJsonName][postNum] = {}
        self.blogBase[listJsonName][postNum]["htmlDir"] = gen_Html
        self.blogBase[listJsonName][postNum]["labels"] = [label.name for label in issue.labels]
        # self.blogBase[listJsonName][postNum]["labelColor"]=self.labelColorInfo[issue.labels[0].name]
        self.blogBase[listJsonName][postNum]["postTitle"] = issue.title
        self.blogBase[listJsonName][postNum]["postUrl"] = urllib.parse.quote(
            gen_Html[len(self.root_dir) :]
        )

        self.blogBase[listJsonName][postNum]["postSourceUrl"] = (
            "https://github.com/" + self.repo_name + "/issues/" + str(issue.number)
        )
        self.blogBase[listJsonName][postNum]["commentNum"] = issue.get_comments().totalCount
        self.blogBase[listJsonName][postNum]["wordCount"] = len(issue.body)

        if issue.body is None:
            self.blogBase[listJsonName][postNum]["description"] = ""
        else:
            if self.blogBase["rssSplit"] == "sentence":
                if self.blogBase["i18n"] == "CN":
                    period = "。"
                else:
                    period = "."
            else:
                period = self.blogBase["rssSplit"]
            self.blogBase[listJsonName][postNum]["description"] = (
                issue.body.split(period)[0] + period
            )

        self.blogBase[listJsonName][postNum]["top"] = 0
        for event in issue.get_events():
            if event.event == "pinned":
                self.blogBase[listJsonName][postNum]["top"] = 1
            elif event.event == "unpinned":
                self.blogBase[listJsonName][postNum]["top"] = 0

        try:
            postConfig = json.loads(issue.body.split(NEWLINE_CHAR)[-1:][0].split("##")[1])
            print("Has Custom JSON parameters")
            print(postConfig)
        except Exception as e:
            print(e)
            postConfig = {}

        if "timestamp" in postConfig:
            self.blogBase[listJsonName][postNum]["createdAt"] = postConfig["timestamp"]
        else:
            self.blogBase[listJsonName][postNum]["createdAt"] = int(
                time.mktime(issue.created_at.timetuple())
            )

        if "style" in postConfig:
            self.blogBase[listJsonName][postNum]["style"] = self.blogBase["style"] + str(
                postConfig["style"]
            )
        else:
            self.blogBase[listJsonName][postNum]["style"] = self.blogBase["style"]

        if "script" in postConfig:
            self.blogBase[listJsonName][postNum]["script"] = self.blogBase["script"] + str(
                postConfig["script"]
            )
        else:
            self.blogBase[listJsonName][postNum]["script"] = self.blogBase["script"]

        if "ogImage" in postConfig:
            self.blogBase[listJsonName][postNum]["ogImage"] = postConfig["ogImage"]
        else:
            self.blogBase[listJsonName][postNum]["ogImage"] = self.blogBase["ogImage"]

        thisTime = datetime.datetime.fromtimestamp(
            self.blogBase[listJsonName][postNum]["createdAt"]
        )
        thisTime = thisTime.astimezone(self.TZ)
        thisYear = thisTime.year
        self.blogBase[listJsonName][postNum]["createdDate"] = thisTime.strftime("%Y-%m-%d")
        self.blogBase[listJsonName][postNum]["dateLabelColor"] = self.blogBase["yearColorList"][
            int(thisYear) % len(self.blogBase["yearColorList"])
        ]

        mdFileName = re.sub(r"[<>:/\\|?*\"]|[\0-\31]", "-", issue.title)
        with open(self.backup_dir + mdFileName + ".md", "w", encoding="UTF-8") as f:
            if issue.body is not None:
                f.write(issue.body)
        return listJsonName

    def runAll(self):
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

        issues = self.repo.get_issues()
        for issue in issues:
            self.addOnePostJson(issue)

        for issue in self.blogBase["allPostInfo"].values():
            self.createPostHtml(issue)
        for issue in self.blogBase["subPageInfo"].values():
            self.createPostHtml(issue)

        self.createPostlistHtml()
        self.createFeedXml()
        print("====== create static html end ======")

    def runOne(self, number_str):
        print("====== start create static html ======")
        issue = self.repo.get_issue(int(number_str))
        listJsonName = self.addOnePostJson(issue)

        self.createPostHtml(self.blogBase[listJsonName]["P" + number_str])

        self.createPostlistHtml()
        self.createFeedXml()
        print("====== create static html end ======")


def update_blog(blog: GMEEK):
    if not os.path.exists("blogBase.json"):
        print("blogBase is not exists, runAll")
        blog.runAll()
    else:
        if os.path.exists(blog.root_dir + "rss.xml"):
            with open(blog.root_dir + "rss.xml", "r", encoding="utf-8") as f:
                blog.oldFeedString = f.read()

        if blog.issue_number == "0" or blog.issue_number == "":
            print(f"issue_number=={blog.issue_number}, runAll")
            blog.runAll()
        else:
            print("blogBase is exists and issue_number!=0, runOne")
            with open("blogBase.json", "r") as f:
                oldBlogBase = json.load(f)

            for key, value in oldBlogBase.items():
                blog.blogBase[key] = value

            blog.runOne(blog.issue_number)

    with open("blogBase.json", "w") as f:
        json.dump(blog.blogBase, f, indent=2)


def update_post_list_json(blog):
    print("====== create postList.json file ======")

    blog.blogBase["allPostInfo"] = OrderedDict(
        sorted(
            blog.blogBase["allPostInfo"].items(),
            key=lambda x: x[1]["createdAt"],
            reverse=True,
        )
    )  # 使列表由时间排序

    commentNumSum = 0
    wordCount = 0
    for i in blog.blogBase["allPostInfo"]:
        del blog.blogBase["allPostInfo"][i]["description"]
        del blog.blogBase["allPostInfo"][i]["postSourceUrl"]
        del blog.blogBase["allPostInfo"][i]["htmlDir"]
        del blog.blogBase["allPostInfo"][i]["createdAt"]
        del blog.blogBase["allPostInfo"][i]["script"]
        del blog.blogBase["allPostInfo"][i]["style"]
        del blog.blogBase["allPostInfo"][i]["top"]
        del blog.blogBase["allPostInfo"][i]["ogImage"]

        if "commentNum" in blog.blogBase["allPostInfo"][i]:
            commentNumSum = commentNumSum + blog.blogBase["allPostInfo"][i]["commentNum"]
            del blog.blogBase["allPostInfo"][i]["commentNum"]

        if "wordCount" in blog.blogBase["allPostInfo"][i]:
            wordCount = wordCount + blog.blogBase["allPostInfo"][i]["wordCount"]
            del blog.blogBase["allPostInfo"][i]["wordCount"]

    blog.blogBase["allPostInfo"]["labelColorInfo"] = blog.labelColorInfo

    with open(blog.root_dir + "postList.json", "w") as f:
        json.dump(blog.blogBase["allPostInfo"], f, indent=2)
    return commentNumSum, wordCount


def update_readme_md(blog, commentNumSum, wordCount):
    print("====== update readme file ======")
    workspace_path = os.environ.get("GITHUB_WORKSPACE")

    readme = (
        f'# {blog.blogBase["title"]} :link: {blog.blogBase["homeUrl"]} {NEWLINE_CHAR}'
        f'- :page_facing_up: [{len(blog.blogBase["allPostInfo"]) - 1}]({blog.blogBase["homeUrl"]}/tag.html) {NEWLINE_CHAR}'
        f'- :speech_balloon: {commentNumSum} {NEWLINE_CHAR}'
        f'- :hibiscus: {wordCount} {NEWLINE_CHAR}'
        f'- :alarm_clock: {datetime.datetime.now(blog.TZ).strftime("%Y-%m-%d %H:%M:%S")} {NEWLINE_CHAR}'
        f'---{NEWLINE_CHAR}'
        '*Powered by :heart: [Gmeek](https://github.com/Meekdai/Gmeek){NEWLINE_CHAR}*'
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

    update_blog(blog)
    commentNumSum, wordCount = update_post_list_json(blog)
    if os.environ.get("GITHUB_EVENT_NAME") != "schedule":
        update_readme_md(blog, commentNumSum, wordCount)


if __name__ == "__main__":
    main()
