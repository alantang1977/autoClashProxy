import os
import sys
import requests
import websocket
import time
import json
import yaml
import random

from concurrent.futures import ThreadPoolExecutor, as_completed

def getPortAndSecret(args, safePath):
    clashVergeConfig = yaml.load(open(os.path.join(safePath, "config.yaml"), encoding='utf8').read(), Loader=yaml.FullLoader)
    return clashVergeConfig["external-controller"].split(":")[1], clashVergeConfig["secret"]

class clashAPI:
    def __init__(self, args):
        self.uiIP = args.uiIP
        self.baseUrl = f"http://{self.uiIP}"
        self.controllerPort = args.uiPort #登录clash web ui的端口
        self.mixedPort = args.mixedPort #http代理端口

        self.timeout = args.timeout #延迟测试超时时间
        self.delayUrl = args.delayUrl #延迟测试需要的url

        self.secret = args.secret #登录clash web ui所需要的秘钥
        self.authorization = {"Authorization": f"Bearer {self.secret}"}

        #self.testUrl = "https://www.youtube.com/s/desktop/c01ea7e3/img/logos/favicon.ico" #生成proxy group设置里所需要的url

        self.httpProxy = f"{self.baseUrl}:{self.mixedPort}"
        self.httpsProxy = f"{self.baseUrl}:{self.mixedPort}"

    def queryProxyDelay(self, proxy):
        proxyName = proxy['name']

        delay = self.timeout + 10 #默认节点延迟时间
        message = f"{proxyName}: timeout"

        url = f"{self.baseUrl}:{self.controllerPort}/proxies/{proxyName}/delay"
        params = {"timeout": self.timeout, "url": self.delayUrl}
        queryResult = eval(requests.get(url, headers=self.authorization, params=params).text)

        if("delay" in queryResult):
            delay = queryResult["delay"]
            message = f"{proxyName}: {delay}"
        elif("message" in queryResult):
            message = f"{proxyName}: " + queryResult["message"]
            proxy = None
        else:
            print("未知message内容:", queryResult)
            sys.exit(1)

        return (proxy, message, delay)

    def queryDNS(self, host):
        ip = "127.0.0.1"

        url = f"{self.baseUrl}:{self.controllerPort}/dns/query?name={host}"
        message = requests.get(url, headers=self.authorization)
        if ("Answer" in message.text):
            answer = json.loads(message.text)["Answer"]
            for data in answer:
                if (data['type'] == 1):
                    ip = data['data']
                    break

        return ip

    def loadConfig(self, configPath, retry):
        print(f"开始加载配置文件：{configPath}")
        url = f"{self.baseUrl}:{self.controllerPort}/configs"

        param = {"force": "true"}
        body = {"path": configPath}

        bLoadSuccessful = False
        for i in range(retry):
            print(f"开始第{i + 1}次加载配置文件：", end="", flush=True)
            message = requests.put(url, headers=self.authorization, params=param, json=body)
            code = message.status_code

            if code == 204:
                print("配置文件加载成功")
                bLoadSuccessful = True
                break
            else:
                print(message.text)
                print("配置文件加载失败")
                time.sleep(2)

            if (i == (retry - 1)):
                print("达到最大重试次数，退出加载配置。")

        return bLoadSuccessful

    def restart(self):
        url = f"{self.baseUrl}:{self.controllerPort}/restart"
        message = requests.post(url, headers=self.authorization)
        if (message.status_code == 200):
            print("成功发送重启内核命令")
        else:
            print(message.text)
            print("发送重启内核命令失败")

    def flushFakeIp(self):
        url = f"{self.baseUrl}:{self.controllerPort}/cache/fakeip/flush"
        message = requests.post(url, headers=self.authorization)
        if (message.status_code == 204):
            print("成功执行flush fakeip命令")
        else:
            print(message)
            print("执行flush fakeip命令失败")

    def groupDelay(self, groupName):
        url = f"{self.baseUrl}:{self.controllerPort}/group/{groupName}/delay"
        params = {"timeout": self.timeout, "url": self.delayUrl}
        message = requests.get(url, headers=self.authorization, params=params)
        print(message.text)

        return json.loads(message.text)

    def groupProxy(self, groupName):
        url = f"{self.baseUrl}:{self.controllerPort}/group/{groupName}"
        message = requests.get(url, headers=self.authorization)
        print(message.text)

        return json.loads(message.text)

    def printLogs(self, ws, string, type, continue_flag):
        message = json.loads(string)
        currentTTime = time.ctime()
        print("[{}] {}: {}".format(currentTTime, message["type"], message["payload"]))

    def recivelogs(self, level="info"):
        url = f"ws://{self.uiIP}:{self.controllerPort}/logs?level={level}"
        logs = websocket.WebSocketApp(url, header=[f"Authorization: Bearer {self.secret}"], on_data=self.printLogs)
        logs.run_forever()

class clashConfig:
    def __init__(self, args):
        self.clash = clashAPI(args)
        self.defaultFile = args.defaultFile #生成配置文件所需要的模板文件，里面会设置好ruler、dns和tun等clash配置
        self.file = args.configFile #最终生成的配置文件
        self.requestsProxy = {'http':  self.clash.httpProxy, 'https': self.clash.httpsProxy} #进行网络请求时设置的代理
        self.minInConfig = args.minProxyInConfig #生成配置文件需要的最少的节点数量
        self.maxInConfig = args.maxProxyInConfig #生成配置文件中所允许的最大节点数量。如果数量过多，后续将需要较多时间来查询节点归属地和延迟测试
        self.maxAfterDelay = args.maxProxyAfterDelay #经过延迟测试后，允许输出的最大节点数量
        self.interval = args.interval #clash代理组节点检测时间间隔
        self.tunStack = args.tunStack #tun模式堆栈，可用值： system/gvisor/mixed

        if (self.minInConfig > self.maxAfterDelay):
            print(f"延迟测试输出的节点数量:{self.maxAfterDelay} 小于 配置文件所需要的最小节点数量:{self.minInConfig}。请检查相关设置")
            sys.exit(1)

        if (self.minInConfig > self.maxInConfig):
            print(f"配置文件中最大节点数量:{self.maxInConfig} 小于 配置文件所需要的最小节点数量:{self.minInConfig}。请检查相关设置")
            sys.exit(1)

    def getPorxyCountry(self, proxy):
        country = "查询未返回结果"
        try:
            ip = proxy['server']
            if (not ip.replace(".", "").isdigit()):
                ip = self.clash.queryDNS(ip)

            data = requests.get(f"http://ip.plyz.net/ip.ashx?ip={ip}", proxies=self.requestsProxy).text
            if (len(data) != 0):
                country = data.split("|")[1].split()[0]
                if (country == "中国"):
                    province = data.split("|")[1].split()[1]
                    if (province in ["香港", "台湾", "澳门"]):
                        country = country + province
                    else:
                        country = "中国大陆"
        except Exception as e:
            print(e)

        if (country == "内网IP"):
            country = "未知地区"

        message = f"{proxy['server']} {country}"
        return (proxy, country, message)

    def createGroup(self, name, groupType, proxies, bIsProviderGroup = False):
        allType = ['select', 'load-balance', 'url-test', 'fallback']

        assert(groupType in allType)
        assert(len(proxies) > 0)

        group = {
            "name"     : name,
            "type"     : groupType,
        }

        if (bIsProviderGroup):
            group['use'] = proxies
        else:
            group['proxies'] = proxies

        if(groupType != "select"):
            group['url'] = self.clash.delayUrl
            group["interval"] = self.interval

        return group

    def createSpecialGroup(self, proxiesNames, groupName, excludeLocation):
        group = []
        proxies = [proxy for proxy in proxiesNames if proxy.split('-')[0] not in excludeLocation]
        if (len(proxies) > 0):
            select = self.createGroup(groupName, "select", [f"{groupName}-延迟最低", f"{groupName}-故障转移", f"{groupName}-负载均衡", f"{groupName}-手动选择", "DIRECT"])
            group.append(self.createGroup(f"{groupName}-延迟最低", "url-test", proxies))
            group.append(self.createGroup(f"{groupName}-故障转移", "fallback", proxies))
            group.append(self.createGroup(f"{groupName}-负载均衡", "load-balance", proxies))
            group.append(self.createGroup(f"{groupName}-手动选择", "select", proxies))
            return True, select, group
        else:
            print(f"{groupName}中符合条件的节点数量为零。不符合配置文件生成条件。")
            return False, None, None

    def createLocationProxyGroup(self, proxyPool):
        print("按照ip地址查询节点所属地区")
        print("利用查询获得的地址给节点重新命名，同时删除不符合要求的节点")

        allCountryCount = dict()
        with ThreadPoolExecutor(max_workers=20) as threadPool:
            allTask = [threadPool.submit(self.getPorxyCountry, proxy) for proxy in proxyPool]

            proxies = []
            countryProxyCount = dict()
            allowCountry = ["美国", "韩国", "日本", "新加坡", "加拿大", "中国大陆", "中国香港"] #只保留这些地方的节点
            for index, future in enumerate(as_completed(allTask)):
                proxy, country, message = future.result()
                print(f"节点{index + 1}: {message}", end=" ")
                allCountryCount[country] = 1 if country not in allCountryCount.keys() else allCountryCount[country] + 1
                if (country in allowCountry):
                    print("归属地符合要求")
                    countryProxyCount[country] = 1 if country not in countryProxyCount.keys() else countryProxyCount[country] + 1
                    proxy['name'] = f"{country}-{countryProxyCount[country]}"
                    proxies.append(proxy)
                else:
                    print("归属地不符合要求，删除")

        print("节点归属地统计：")
        allCountryCount = sorted(allCountryCount.items(), key=lambda x: x[1])
        for country in allCountryCount:
            print('{}: {}'.format(country[0], country[1]))
        print(f"after createLocationProxyGroup, 剩余节点数量{len(proxies)}")
        return proxies

    def creatConfig(self, proxies):
        print("开始生成配置文件")
        print(f"生成配置文件所需的最小节点数量为：{self.minInConfig}")
        print(f"生成配置文件所允许的最大节点数量为：{self.maxInConfig}")

        if(len(proxies) < self.minInConfig):
            print("节点数量不足，不生成clash配置文件")
            return False
        if(len(proxies) > self.maxInConfig):
            print("节点数量过多，只保留所允许的最大节点数量生成配置文件")
            random.shuffle(proxies)
            proxies = proxies[:self.maxInConfig]

        defaultConfig = open(self.defaultFile, encoding='utf8').read()
        config = yaml.load(defaultConfig, Loader=yaml.FullLoader)

        #config["external-controller"] = f"{self.clash.baseUrl}:{self.clash.controllerPort}"
        #config["secret"] = self.clash.secret
        config['tun']['stack'] = self.tunStack

        proxies = self.createLocationProxyGroup(proxies)

        proxiesNames = [proxy['name'] for proxy in proxies]

        config['proxies'] = proxies if config['proxies'] == None else config['proxies'] + proxies

        config['proxy-groups'] = []

        #导入自己购买的机场
        privateGroup = []
        privateGroupName = []
        if (len(config['proxy-providers'].keys()) == 1):
            privateGroup.append(self.createGroup(f"私有节点", "select", list(config['proxy-providers'].keys()), True))
            privateGroupName.append("私有节点")
        else:
            for group in config['proxy-providers'].keys():
                privateGroupName.append(f"私有节点_{group}")
                privateGroup.append(self.createGroup(f"私有节点_{group}", "select", [group], True))

        config['proxy-groups'].append(self.createGroup(f"直连规则", "select", ["DIRECT", "全球互联", "私有节点"]))
        config['proxy-groups'].append(self.createGroup(f"漏网之鱼", "select", ["DIRECT", "全球互联", "私有节点"]))
        config['proxy-groups'].append(self.createGroup(f"全球互联", "select", ["共享节点", "私有节点", "DIRECT"]))
        config['proxy-groups'].append(self.createGroup(f"特殊应用", "select", ["全球互联", "私有节点", "国外节点", "DIRECT"]))
        config['proxy-groups'].append(self.createGroup(f"GAME",    "select", ["DIRECT", "全球互联", "私有节点"]))
        if (len(privateGroup) > 1):
            config['proxy-groups'].append(self.createGroup(f"私有节点", "select", privateGroupName))
        config['proxy-groups'] += privateGroup

        allGroups =[
            #groupName,  排除指定归属地的节点
            ["共享节点",  []],
            ["国外节点",  ["中国香港", "中国大陆"]],
        ]

        bCreateSuccess = True
        allGroup = []
        for i in allGroups:
            bCreateSuccess, select, group = self.createSpecialGroup(proxiesNames, i[0], i[1])
            if (not bCreateSuccess):
                return False
            config['proxy-groups'].append(select)
            allGroup += group
        config['proxy-groups'] += allGroup

        with open(self.file, 'w', encoding='utf-8') as file:
            yaml.dump(config, file, allow_unicode=True)

        print("生成clash配置文件：{}".format(self.file))

        return True

if __name__ == "__main__":
    import sys
    sys.path.append('.')
    from processArgument import *

    args = processArgs(False)
    if (args.safePath):
        args.uiPort, args.secret = getPortAndSecret(args, args.safePath)

    clash = clashAPI(args)
    #clash.groupProxy("手动选择")
    #clash.groupDelay("手动选择")
    if (args.log):
        clash.recivelogs(args.log)
