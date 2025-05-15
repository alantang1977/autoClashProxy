import requests
import yaml

import re

from operator import itemgetter

from concurrent.futures import ThreadPoolExecutor, as_completed

def removeDuplicateNode(proxyPool): #删除重复节点
    checkLists = ["name", "server"]

    allProxy = proxyPool
    for item in checkLists:
        proxiesItem  = []
        proxies = []
        for proxy in allProxy:
            if(proxy[item] in proxiesItem):
                continue
            proxies.append(proxy)
            proxiesItem.append(proxy[item])
        allProxy = proxies

        print(f"after removeDuplicate_{item}, 剩余节点数量{len(allProxy)}")

    return allProxy

def removeNotSupportNode(proxyPool): #删除clash不支持的节点
    notSupportItems = {
        "cipher" : ["ss", None],
        "uuid"   : [],
        "type"   : []
    }

    for item in notSupportItems.keys():
        proxies = []
        for proxy in proxyPool:
            if (item in proxy and proxy[item] in notSupportItems[item]):
                print(f"{item}: {proxy[item]} not support.", proxy)
                continue
            proxies.append(proxy)
        proxyPool = proxies
        print(f"after removeNotSupport_{item}, 剩余节点数量{len(proxies)}")

    return proxies

def addMisskeyNode(proxyPool): #增加缺失的字段
    needKey = {
        "alterId": 0
    }

    proxies = []
    for proxy in proxyPool:
        for key in needKey.keys():
            if (key not in proxy ):
                print(f"miss key:",key,  proxy)
                proxy[key] = needKey[key]
        proxies.append(proxy)

    return proxies

#TLS must be true with h2/grpc network in vmess
def setTLSForVmess(proxyPool):
    proxies = []
    for proxy in proxyPool:
        if (proxy['type'] == "vmess" and "network" in proxy):
            if (proxy['network'] in ["grpc"]):
                proxy['tls'] = True
        proxies.append(proxy)

    return proxies

#有些节点的配置可能不正确，会导致配置文件加载失败
def removeErrorProxy(proxyPool):
    proxies = []
    for proxy in proxyPool:
        if (str(proxy['port']).isdigit()): #节点的port不为数字，就不添加至最终的节点中
            proxies.append(proxy)

    print(f"after removeErrorProxy, 剩余节点数量{len(proxies)}")

    return proxies

def processNodes(proxyPool):
    proxies = removeDuplicateNode(proxyPool)
    proxies = removeNotSupportNode(proxies)
    proxies = removeErrorProxy(proxies)
    proxies = setTLSForVmess(proxies)
    proxies = addMisskeyNode(proxies)

    return proxies

def removeTimeoutProxy(proxies, profile, maxProxy):
    passProxy=[]
    results = []

    print(f"延迟测试超时时间为：{profile.clash.timeout}ms")
    print(f"延迟测试url为：{profile.clash.delayUrl}")
    print(f"测试节点总数为：{len(proxies)}")
    try:
        with ThreadPoolExecutor(max_workers=30) as threadPool:
            allTask = [threadPool.submit(profile.clash.queryProxyDelay, proxy) for proxy in proxies]

            for index, future in enumerate(as_completed(allTask)):
                proxy, message, delay = future.result()
                print(f"节点{index + 1}: {message}")
                if (proxy != None):
                    results.append((proxy, delay))

            print("所有节点延迟测试结束")
            print(f"测试正常节点: {len(results)}/{len(proxies)}")

            chinaProxyCount = 0
            results = sorted(results, key=itemgetter(1)) #对节点按照延迟时间进行排序
            for result in results: #按照排序结果取相应数量的节点
                proxyCountry = result[0]['name'].split('-')[0]
                if ("中国" in proxyCountry):
                    chinaProxyCount += 1
                if (chinaProxyCount / maxProxy > 0.8):
                    print("中国节点数量超过限额，不再添加")
                    continue

                print(f"{result[0]['name']}: {result[1]}ms")
                passProxy.append(result[0])

                if (len(passProxy) == maxProxy):
                    print("获取节点数量已达到设置的最大数量。")
                    break
    except Exception as e:
        print(f"测试发生错误：{e}")

    print(f"after removeTimeoutProxy, 剩余节点数量{len(passProxy)}")

    return passProxy

def downloadProxy(url, requestsProxy):
    print(f"开始下载：{url}")
    download = None
    try:
        req = requests.get(url, proxies=requestsProxy)
        if (req.status_code == 200):
            print(f"{url} 下载完成")
            download =  req.text
        else:
            print(f"{url} 下载失败")
    except Exception as e:
        print(f"{url}：{e}")

    proxies = []
    if (download != None):
        #下载的内容中可能会包含一些html标签等无关内容，需要删除这些多余的内容。
        download = download.replace("!<str> ", "")
        download = download.replace("!&lt;str&gt;", "")
        html = re.compile('<.*?>')
        download = re.sub(html, "", download)
        try:
            file = yaml.load(download, Loader=yaml.FullLoader)
            proxies = file["proxies"] if file["proxies"] != None else []
            print(f"{url}：成功获得节点")
        except Exception as e:
            print(f"{url}：解析节点失败。 Error：{e}")

    return (proxies, url)

def getProxyFromSource(sources, requestsProxy):
    proxyPool = []
    with ThreadPoolExecutor(max_workers=20) as threadPool:
        allTask = [threadPool.submit(downloadProxy, url, requestsProxy) for url in sources]

        for index, future in enumerate(as_completed(allTask)):
            proxies, url = future.result()
            proxyPool += proxies
            print(f"{index + 1}、{url} 处理完成")

    print("全部链接下载完成")
    print("获取节点数量:", len(proxyPool))

    return proxyPool

if __name__ == "__main__":
    pass