import re

from .contracts import AssistantIntent


class IntentClassifier:
    _fund = re.compile(r"基金|净值|持仓|自选")
    _news = re.compile(r"新闻|资讯|事件|热点|消息")
    _market = re.compile(r"A股|a股|上证|深证|创业板|沪深|指数|行情|市场|港股|美股")
    _causal = re.compile(r"为什么|为何|原因|影响|驱动|涨|跌")

    def classify(self, message: str) -> AssistantIntent:
        has_fund = bool(self._fund.search(message))
        has_news = bool(self._news.search(message))
        has_market = bool(self._market.search(message))
        has_causal = bool(self._causal.search(message))
        if has_fund:
            return AssistantIntent.FUND_ANALYSIS if re.search(r"我的|表现|分析|看看|怎么样|影响", message) else AssistantIntent.FUND
        if has_news and has_market and re.search(r"事件|热点", message) and not has_causal:
            return AssistantIntent.MARKET_EVENT
        if has_market and (has_news or has_causal):
            return AssistantIntent.NEWS_MARKET
        if has_news and re.search(r"市场|影响|事件", message):
            return AssistantIntent.MARKET_EVENT
        if has_news:
            return AssistantIntent.NEWS
        if has_market:
            return AssistantIntent.MARKET
        if re.search(r"财经|金融|经济|利率|通胀|汇率", message):
            return AssistantIntent.GENERAL_FINANCE
        return AssistantIntent.UNKNOWN
