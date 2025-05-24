import yaml
import os

import sys
sys.path.append('.')

from processProxy import *
from autoGit import *
from clash import *
from processArgument import *

def parserSourceUrl(sourceFile):
    print(f"从{sourceFile}解析出以下有效的url:")
    allUrls = open(sourceFile, encoding='utf8').read().strip().splitlines()
    allUrl = []
    for url in allUrls:
        if (url.strip().startswith("#") or url.strip().startswith("//")): #删除注释
            continue
        if (url.isspace() or len(url) == 0): #删除空行
            continue
        if (url not in allUrl): #删除重复url
            allUrl.append(url)
            print(url)

    print("解析完成，共获得{}个有效url".format(len(allUrl)))
    return allUrl

def checkNeedUpdate(profile):
    print("开始检测是否需要更新节点：")
    clash = profile.clash

    checkGroupName = "手动选择-PROXY"
    allProxy = clash.groupProxy(checkGroupName)

    if ("all" in allProxy):
        valid = clash.groupDelay(checkGroupName)
        if (len(valid) / len(allProxy['all']) < 0.5):
            print("有效节点数量不足一半，需要更新")
            return True
        elif (len(allProxy['all']) < profile.maxAfterDelay * 0.8):
            print("总节点数过少，需要更新")
            return True
        else:
            return False

    return True

args = processArgs()
profile = clashConfig(args)

if (args.flushFakeip):
    profile.clash.flushFakeIp()
    sys.exit(0)

if (args.noDownload and args.local):
    print("error: argument --noDownload: not allowed with argument --local")
    sys.exit(1)

if (args.noDownload and args.download):
    print("error: argument --noDownload: not allowed with argument --download")
    sys.exit(1)

bNoDownload = args.noDownload
proxies = None
configPath = f"{profile.file}"

if (args.update and (not args.noCheck) and (not checkNeedUpdate(profile))):
    print("当前配置文件中存在足够多的有效节点，无需更新")
    sys.exit(0)

#处理本地的clash配置文件，删除里面不符合要求的节点，生成配置文件。
if (args.local or bNoDownload):
    print(f"开始处理配置文件：{profile.file}。")
    proxies = yaml.load(open(profile.file, encoding='utf8').read(), Loader=yaml.FullLoader)["proxies"]
    bNoDownload = True

#如果没有指定noDownload，会根据urlfile从网上下载节点。删除里面不符合要求的节点，生成配置文件。
if ((args.download or args.update) and (not bNoDownload)):
    print("开始下载公开节点。")
    sources = parserSourceUrl(args.urlfile)
    proxies = getProxyFromSource(sources, profile.requestsProxy)

if (len(proxies) < profile.minInConfig):
    print(f"获取的节点数量为：{len(proxies)}。少于生成配置文件所需要的最低数量：{profile.minInConfig}")
    print("节点数量不足。程序退出。")
    sys.exit(1)

proxies = processNodes(proxies)
bSuccess = profile.creatConfig(proxies)

if (args.update):
    if (bSuccess and profile.clash.loadConfig(configPath, args.retry)): #成功生成配置文件后，在clash中加载生成的配置文件，准备对所有节点进行延迟测试。
        bSuccess = False
        proxies = yaml.load(open(profile.file, encoding='utf8').read(), Loader=yaml.FullLoader)["proxies"]
        proxies = removeTimeoutProxy(proxies, profile, profile.maxAfterDelay) #对配置文件中的所有节点进行延迟测试，删除延迟时间不符合要求的节点。
        bSuccess = profile.creatConfig(proxies)
        if (not bSuccess):
            checkoutFile(profile.file) #经过延迟测试后，可能会出现节点数量少于最低要求的情况，这样就需要回退配置文件。
        profile.clash.loadConfig(configPath, args.retry) #延迟测试结束，加载配置文件。
        #profile.clash.restart()
    else:
        bSuccess = False

    if (not bSuccess):
        print("配置文件更新失败")

if (bSuccess and args.push):
    pushFile(profile.file, args.retry)