import sys
import requests
import time
import json
import yaml
import random

from concurrent.futures import ThreadPoolExecutor, as_completed

class clashAPI:
    def __init__(self, args):
        self.baseUrl = args.uiUrl
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
        print(f"开始加载配置文件{configPath}。")
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

        if (self.minInConfig > self.maxAfterDelay):
            print(f"延迟测试输出的节点数量:{self.maxAfterDelay} 小于 配置文件所需要的最小节点数量:{self.minInConfig}。请检查相关设置")
            sys.exit(1)

        if (self.minInConfig > self.maxInConfig):
            print(f"配置文件中最大节点数量:{self.maxInConfig} 小于 配置文件所需要的最小节点数量:{self.minInConfig}。请检查相关设置")
            sys.exit(1)

    def getPorxyCountry(self, proxy):
        country = "未知地区"
        try:
            ip = proxy['server']
            if (not ip.replace(".", "").isdigit()):
                ip = self.clash.queryDNS(ip)

            data = requests.get(f"http://ip.plyz.net/ip.ashx?ip={ip}", proxies=self.requestsProxy).text
            if (len(data) != 0):
                country = data.split("|")[1].split()[0]
                if (country == "中国"):
                    province = data.split("|")[1].split()[1]
                    if ("香港" in province or "台湾" in province or "澳门" in province):
                        country = country + province
                    else:
                        country = "中国大陆"
        except Exception as e:
            print(e)

        if (country == "内网IP"):
            country = "未知地区"

        message = f"{proxy['server']} {country}"
        return (proxy, country, message)

    def createGroup(self, name, groupType, proxies):
        allType = ['select', 'load-balance', 'url-test', 'fallback']
        assert(groupType in allType)

        group = {
            "name"     : name,
            "type"     : groupType,
            "proxies"  : proxies,
        }

        if(groupType != "select"):
            group['url'] = self.clash.delayUrl
            group["interval"] = self.interval

        return group

    def createSpecialGroup(self, proxiesNames, excludeLocation, config, groupName):
        tiktokProxies = [proxy for proxy in proxiesNames if proxy.split('-')[0] not in excludeLocation]
        if (len(tiktokProxies) >= 4):
            config['proxy-groups'].append(self.createGroup(groupName, "select", [f"延迟最低-{groupName}", f"故障转移-{groupName}", f"负载均衡-{groupName}", f"手动选择-{groupName}", "DIRECT"]))
            config['proxy-groups'].append(self.createGroup(f"延迟最低-{groupName}", "url-test", tiktokProxies))
            config['proxy-groups'].append(self.createGroup(f"故障转移-{groupName}", "fallback", tiktokProxies))
            config['proxy-groups'].append(self.createGroup(f"负载均衡-{groupName}", "load-balance", tiktokProxies))
            config['proxy-groups'].append(self.createGroup(f"手动选择-{groupName}", "select", tiktokProxies))
            return True
        else:
            print("包含节点数量过少，不满足条件")
            return False

    def createLocationProxyGroup(self, proxies):
        print("按照ip地址查询节点所属地区")
        print("利用查询获得的地址给节点重新命名")

        location = dict()
        with ThreadPoolExecutor(max_workers=20) as threadPool:
            allTask = [threadPool.submit(self.getPorxyCountry, proxy) for proxy in proxies]

            for index, future in enumerate(as_completed(allTask)):
                proxy, country, message = future.result()
                print(f"节点{index + 1}: {message}")
                countryGroup = location[country] if (country in location) else self.createGroup(country, "url-test", [])
                proxy['name'] = f"{country}-{len(countryGroup['proxies']) + 1}"
                countryGroup['proxies'].append(proxy['name'])
                location[country] = countryGroup

        return location

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

        self.createLocationProxyGroup(proxies)

        proxiesNames = [proxy['name'] for proxy in proxies]

        config['proxies'] = proxies if config['proxies'] == None else config['proxies'] + proxies

        config['proxy-groups'] = []

        config['proxy-groups'].append(self.createGroup("PROXY", "select", ["延迟最低", "故障转移", "负载均衡", "手动选择", "DIRECT"]))
        config['proxy-groups'].append(self.createGroup("漏网之鱼", "select", ["延迟最低", "故障转移", "负载均衡", "手动选择", "DIRECT"]))
        config['proxy-groups'].append(self.createGroup("媒体影音", "select", ["延迟最低", "故障转移", "负载均衡", "手动选择", "DIRECT"]))

        config['proxy-groups'].append(self.createGroup("延迟最低", "url-test", proxiesNames))
        config['proxy-groups'].append(self.createGroup("故障转移", "fallback", proxiesNames))
        config['proxy-groups'].append(self.createGroup("负载均衡", "load-balance", proxiesNames))
        config['proxy-groups'].append(self.createGroup("手动选择", "select", proxiesNames))

        bCreateSuccess = True
        bCreateSuccess |= self.createSpecialGroup(proxiesNames, ["中国香港", "中国大陆"], config, "TIKTOK")
        bCreateSuccess |= self.createSpecialGroup(proxiesNames, ["中国香港", "中国大陆"], config, "OPENAI")
        bCreateSuccess |= self.createSpecialGroup(proxiesNames, [], config, "DNS")

        if (not bCreateSuccess):
            return False

        # config['proxy-groups'] += allCountry
        with open(self.file, 'w', encoding='utf-8') as file:
            yaml.dump(config, file, allow_unicode=True)

        print("生成clash配置文件：{}".format(self.file))

        return True

if __name__ == "__main__":
    clash = clashAPI()
    clash.groupProxy("手动选择")
    clash.groupDelay("手动选择")
