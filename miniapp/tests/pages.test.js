const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')

const root = path.resolve(__dirname, '..')
const api = require('../services/api')

function loadPage(relativePath) {
  let definition
  global.Page = (value) => {
    definition = value
  }
  const absolutePath = path.join(root, relativePath)
  delete require.cache[require.resolve(absolutePath)]
  require(absolutePath)
  return definition
}

function createContext(definition) {
  const context = {
    ...definition,
    data: JSON.parse(JSON.stringify(definition.data)),
    setData(update) {
      Object.assign(this.data, update)
    }
  }
  return context
}

global.wx = {
  getAccountInfoSync: () => ({ miniProgram: { envVersion: 'develop' } }),
  request: () => {},
  stopPullDownRefresh: () => {},
  navigateTo: () => {},
  redirectTo: () => {},
  showToast: () => {},
  showModal: () => {},
  setClipboardData: () => {},
  setNavigationBarTitle: () => {}
}

test('app configuration declares all pages and five tabs', () => {
  const config = JSON.parse(fs.readFileSync(path.join(root, 'app.json'), 'utf8'))
  assert.equal(config.tabBar.list.length, 5)
  assert.deepEqual(config.tabBar.list.map((item) => item.text), ['首页', '新闻', '行情', '基金', 'AI'])
  for (const item of config.tabBar.list) {
    assert.equal(fs.existsSync(path.join(root, item.iconPath)), true)
    assert.equal(fs.existsSync(path.join(root, item.selectedIconPath)), true)
  }
  for (const page of config.pages) {
    for (const extension of ['js', 'json', 'wxml', 'wxss']) {
      assert.equal(fs.existsSync(path.join(root, `${page}.${extension}`)), true)
    }
  }
})

test('dashboard supports success, empty, refresh and error states', async () => {
  const definition = loadPage('pages/index/index.js')
  const context = createContext(definition)
  let refreshStopped = false
  global.wx.stopPullDownRefresh = () => {
    refreshStopped = true
  }

  api.getDashboard = async () => ({
    top_news: [{ id: '1', title: '中文财经快讯', source: '中新网财经', importance: 5 }],
    latest_events: [{ id: '2', title: '财经事件', occurred_at: '2026-08-08T00:00:00Z' }],
    system_status: '中文新闻源未配置',
    generated_at: '2026-08-08T00:00:00Z'
  })
  api.getMarket = async () => ({
    items: [{ symbol: 'sh000001', name: '上证指数', price: 100, change: 1, change_percent: 1 }]
  })
  api.getFundWatchlist = async () => ({ items: [] })
  api.getMarketHistory = async () => ({ status: 'unavailable', items: [] })
  await context.loadDashboard(true)
  assert.equal(context.data.status, 'success')
  assert.equal(context.data.featuredNews.importanceText, '★★★★★')
  assert.equal(context.data.newsSourceStatus, '中文新闻源未配置')
  assert.equal(refreshStopped, true)

  api.getDashboard = async () => ({ top_news: [], latest_events: [] })
  await context.loadDashboard()
  assert.equal(context.data.status, 'success')
  assert.equal(context.data.featuredNews, null)

  api.getDashboard = async () => {
    throw new Error('offline')
  }
  api.getMarket = async () => { throw new Error('offline') }
  api.getFundWatchlist = async () => { throw new Error('offline') }
  api.getMarketHistory = async () => { throw new Error('offline') }
  await context.loadDashboard()
  assert.equal(context.data.status, 'error')
})

test('market page groups quotes, refreshes and handles unavailable data', async () => {
  const definition = loadPage('pages/market/market.js')
  const context = createContext(definition)
  let toastTitle = ''
  global.wx.showToast = ({ title }) => {
    toastTitle = title
  }
  api.getMarket = async () => ({
    generated_at: '2026-08-08T00:00:00Z',
    items: [
      {
        symbol: 'sh000001',
        name: '上证指数',
        market: 'CN',
        price: 100,
        change: 1,
        change_percent: 1,
        market_status: 'closed'
      },
      {
        symbol: 'hk_hsi',
        name: '恒生指数',
        market: 'HK',
        price: null,
        change: null,
        change_percent: null,
        market_status: 'unavailable'
      }
    ]
  })
  await context.loadMarket({ manual: true })
  assert.equal(context.data.status, 'success')
  assert.equal(context.data.groups.length, 2)
  assert.equal(context.data.visibleItems[0].name, '上证指数')
  assert.equal(context.data.groups[1].items[0].priceText, '暂无数据')
  assert.equal(toastTitle, '刷新成功')

  api.getMarket = async () => {
    throw new Error('offline')
  }
  await context.loadMarket()
  assert.equal(context.data.status, 'error')
})

test('market detail uses Chinese presentation and supports failures', async () => {
  const definition = loadPage('pages/market-detail/market-detail.js')
  const context = createContext(definition)
  context.data.symbol = 'us_ixic'
  api.getMarketDetail = async () => ({
    symbol: 'us_ixic',
    name: '纳斯达克指数',
    market: 'US',
    price: 200,
    change: -2,
    change_percent: -1,
    timestamp: '2026-08-08T00:00:00Z',
    market_status: 'closed',
    source: 'Yahoo Finance'
  })
  await context.loadQuote()
  assert.equal(context.data.status, 'success')
  assert.equal(context.data.quote.marketStatusText, '已收盘')
  assert.equal(context.data.quote.changeClass, 'fall')

  api.getMarketDetail = async () => {
    throw new Error('offline')
  }
  await context.loadQuote()
  assert.equal(context.data.status, 'error')
})

test('market history switches periods and handles real, empty and error states', async () => {
  const context = createContext(loadPage('pages/market-detail/market-detail.js'))
  context.data.symbol = 'sh000001'
  api.getMarketHistory = async () => ({
    symbol: 'sh000001',
    period: 'day',
    range: '1m',
    items: [{ timestamp: '2026-08-08T00:00:00+08:00', open: 10, high: 12, low: 9, close: 11, volume: 100 }],
    source: 'BaoStock',
    as_of: '2026-08-08T00:00:00+08:00',
    is_delayed: true,
    timezone: 'Asia/Shanghai',
    status: 'available'
  })
  await context.loadHistory()
  assert.equal(context.data.historyStatus, 'success')
  assert.equal(context.data.history.source, 'BaoStock')

  context.selectPeriod({ currentTarget: { dataset: { value: 'intraday' } } })
  assert.equal(context.data.selectedRange, '1d')

  api.getMarketHistory = async () => ({ status: 'unavailable', items: [], message: '暂无历史行情数据' })
  await context.loadHistory()
  assert.equal(context.data.historyStatus, 'unavailable')

  api.getMarketHistory = async () => { throw new Error('offline') }
  await context.loadHistory()
  assert.equal(context.data.historyStatus, 'error')
})

test('news page supports initial load, pagination and empty state', async () => {
  const definition = loadPage('pages/news/news.js')
  const context = createContext(definition)
  let call = 0
  api.getNews = async () => {
    call += 1
    return call === 1
      ? { items: [{ id: '1', title: 'First', importance: 4 }], has_more: true }
      : { items: [{ id: '2', title: 'Second', importance: 3 }], has_more: false }
  }
  await context.loadNews(true)
  await context.loadNews(false)
  assert.equal(context.data.items.length, 2)
  assert.equal(context.data.hasMore, false)

  api.getNews = async () => ({ items: [], has_more: false })
  await context.loadNews(true)
  assert.equal(context.data.status, 'empty')
})

test('news category tabs filter only existing backend categories', async () => {
  const context = createContext(loadPage('pages/news/news.js'))
  api.getNews = async () => ({
    items: [
      { id: '1', title: '宏观新闻', category: 'macro', importance: 5 },
      { id: '2', title: '公司新闻', category: '公司事件', importance: 3 },
      { id: '3', title: '物价新闻', category: '宏观经济指标', importance: 4 }
    ],
    has_more: false
  })
  await context.loadNews(true)
  context.selectCategory({ currentTarget: { dataset: { key: 'company' } } })
  assert.equal(context.data.items.length, 1)
  assert.equal(context.data.items[0].title, '公司新闻')
  context.selectCategory({ currentTarget: { dataset: { key: 'macro' } } })
  assert.equal(context.data.items.length, 2)
  context.selectCategory({ currentTarget: { dataset: { key: 'international' } } })
  assert.equal(context.data.status, 'empty')
})

test('news page and detail page hide request failures behind error state', async () => {
  const news = createContext(loadPage('pages/news/news.js'))
  api.getNews = async () => {
    throw new Error('private backend error')
  }
  await news.loadNews(true)
  assert.equal(news.data.status, 'error')

  const detail = createContext(loadPage('pages/news-detail/news-detail.js'))
  detail.data.id = 'missing'
  api.getNewsDetail = async () => {
    throw new Error('private backend error')
  }
  await detail.loadDetail()
  assert.equal(detail.data.status, 'error')
})

test('news detail maps analysis, impacts and related news', async () => {
  const detail = createContext(loadPage('pages/news-detail/news-detail.js'))
  detail.data.id = '1'
  api.getNewsDetail = async () => ({
    id: '1',
    title: 'Headline',
    importance: 5,
    published_at: '2026-08-08T00:00:00Z',
    analysis: { summary: 'Analysis' },
    market_impacts: [{ asset: 'gold', direction: 'bullish' }],
    event: { title: 'Event' },
    related_news: [{ id: '2', title: 'Related', importance: 4 }]
  })
  await detail.loadDetail()
  assert.equal(detail.data.status, 'success')
  assert.equal(detail.data.detail.market_impacts.length, 1)
  assert.equal(detail.data.detail.related_news[0].importanceText, '★★★★')
})

test('fund center separates official NAV, experimental estimate and position returns', async () => {
  const definition = loadPage('pages/fund/fund.js')
  const context = createContext(definition)
  let toastTitle = ''
  global.wx.showToast = ({ title }) => {
    toastTitle = title
  }
  api.getFundWatchlist = async () => ({
    provider_configured: true,
    generated_at: '2026-08-08T00:00:00Z',
    items: [{
      code: '000001.OF',
      name: '测试基金',
      fund_type: '混合型',
      official_nav: {
        value: 1.25,
        source: 'Tushare',
        as_of: '2026-08-07',
        is_estimate: false,
        is_stale: false
      },
      intraday_estimate: {
        value: 1.3,
        source: '天天基金实验性估值',
        as_of: '2026-08-08T06:00:00Z',
        is_estimate: true,
        is_stale: false
      },
      estimate_change_percent: 1.23,
      market_status: 'closed',
      position: {
        shares: 100,
        average_cost: 1,
        official_market_value: 125,
        official_profit: 25,
        official_profit_rate: 25,
        estimated_market_value: 130,
        estimated_profit: 30,
        estimated_profit_rate: 30
      }
    }]
  })
  await context.loadWatchlist({ manual: true })
  assert.equal(context.data.status, 'success')
  assert.equal(context.data.items[0].navText, '1.2500')
  assert.equal(context.data.items[0].estimateText, '1.3000')
  assert.equal(context.data.items[0].estimateChangeText, '+1.23%')
  assert.equal(context.data.items[0].position.estimatedProfitText, '+30.00')
  assert.equal(context.data.items[0].marketStatusText, '休市，展示最近正式净值')
  assert.equal(toastTitle, '刷新完成')

  api.getFundWatchlist = async () => ({
    provider_configured: false,
    items: [],
    message: '基金数据源尚未配置，正式净值和重仓股暂无数据'
  })
  await context.loadWatchlist()
  assert.equal(context.data.status, 'empty')
  assert.match(context.data.providerMessage, /尚未配置/)
})

test('fund center searches and adds a real provider result', async () => {
  const context = createContext(loadPage('pages/fund/fund.js'))
  context.data.query = '华夏'
  api.searchFunds = async () => ({
    provider_configured: true,
    items: [{ code: '000001.OF', name: '华夏成长', source: 'Tushare' }]
  })
  let addedCode = ''
  api.addFundWatchlist = async (code) => {
    addedCode = code
  }
  api.getFundWatchlist = async () => ({ items: [], generated_at: null })
  await context.search()
  assert.equal(context.data.searchStatus, 'success')
  assert.equal(context.data.searchItems[0].source, 'Tushare')
  await context.addFund({ currentTarget: { dataset: { code: '000001.OF' } } })
  assert.equal(addedCode, '000001.OF')
})

test('fund detail distinguishes official NAV and experimental valuation', async () => {
  const context = createContext(loadPage('pages/fund-detail/fund-detail.js'))
  context.data.code = '000001.OF'
  api.getFundDetail = async () => ({
    code: '000001.OF',
    name: '华夏成长',
    official_nav: {
      value: 1.25,
      source: 'Tushare',
      as_of: '2026-08-07',
      is_estimate: false,
      is_stale: false
    },
    intraday_estimate: {
      value: 1.3,
      source: '天天基金实验性估值',
      as_of: '2026-08-08T06:00:00Z',
      is_estimate: true,
      is_stale: false
    },
    estimate_change_percent: 1.23,
    market_status: 'closed',
    source: 'Tushare',
    holdings_report_date: '2026-06-30',
    holdings: [{ symbol: '600000.SH', weight_percent: 5, report_date: '2026-06-30' }],
    position: null,
    is_favorite: false,
    provider_configured: true
  })
  await context.loadFund()
  assert.equal(context.data.status, 'success')
  assert.equal(context.data.fund.navText, '1.2500')
  assert.equal(context.data.fund.estimateText, '1.3000')
  assert.equal(context.data.fund.estimateStatusText, '盘中估算：休市')
  assert.equal(context.data.fund.holdingsReportDateText, '2026年6月30日')

  context.data.sharesInput = '100'
  context.data.averageCostInput = '1.10'
  let saved = null
  api.saveFundPosition = async (code, value) => {
    saved = { code, value }
  }
  await context.savePosition()
  assert.deepEqual(saved, {
    code: '000001.OF',
    value: { shares: 100, average_cost: 1.1 }
  })
})

test('fund history displays only official NAV and reports unauthorized source', async () => {
  const context = createContext(loadPage('pages/fund-detail/fund-detail.js'))
  context.data.code = '000001.OF'
  api.getFundNavHistory = async () => ({
    code: '000001.OF',
    range: '3m',
    items: [{ nav_date: '2026-08-07', unit_nav: 1.2, adj_nav: 1.3 }],
    source: 'Tushare',
    as_of: '2026-08-07',
    is_estimate: false,
    status: 'available'
  })
  await context.loadNavHistory()
  assert.equal(context.data.navHistoryStatus, 'success')
  assert.equal(context.data.navHistory.is_estimate, false)

  api.getFundNavHistory = async () => ({
    items: [],
    source: 'Tushare',
    status: 'unauthorized',
    message: '历史净值数据源未授权'
  })
  await context.loadNavHistory()
  assert.equal(context.data.navHistoryStatus, 'unauthorized')
  assert.match(context.data.navHistory.stateText, /未授权/)
})

test('chart utilities sort valid points and never invent missing values', () => {
  const { bounds, normalizeMarketPoints, normalizeNavPoints } = require('../utils/chart')
  const market = normalizeMarketPoints([
    { timestamp: '2026-08-08', open: 2, high: 3, low: 1, close: 2.5 },
    { timestamp: '2026-08-07', open: 1, high: 2, low: 0.5, close: 1.5 },
    { timestamp: '2026-08-06', open: null, high: 2, low: 1, close: 1.5 }
  ])
  assert.equal(market.length, 2)
  assert.equal(market[0].timestamp, '2026-08-07')
  const nav = normalizeNavPoints([
    { nav_date: '2026-08-07', unit_nav: 1.2, adj_nav: null },
    { nav_date: '2026-08-08', unit_nav: null, adj_nav: null }
  ])
  assert.deepEqual(nav, [{ timestamp: '2026-08-07', value: 1.2 }])
  assert.deepEqual(bounds([2, 2]), { min: 1.98, max: 2.02 })
})

test('M12 shared states, Chinese product copy and responsive guards are present', () => {
  for (const file of ['components/state-panel/state-panel.wxml', 'components/mini-trend/mini-trend.wxml']) {
    assert.equal(fs.existsSync(path.join(root, file)), true)
  }
  const allWxml = fs.readdirSync(path.join(root, 'pages'), { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => fs.readFileSync(path.join(root, 'pages', entry.name, `${entry.name}.wxml`), 'utf8'))
    .join('\n')
  assert.doesNotMatch(allWxml, /M10 将支持|即将上线|Loading\.\.\./)
  assert.match(allWxml, /历史净值数据源|navHistoryStatus/)
  const styles = fs.readFileSync(path.join(root, 'app.wxss'), 'utf8')
  assert.match(styles, /safe-area-inset-bottom/)
  assert.match(styles, /--color-rise/)
  assert.match(styles, /--space-6/)
  const detailStyles = fs.readFileSync(path.join(root, 'pages/news-detail/news-detail.wxss'), 'utf8')
  assert.match(detailStyles, /overflow-wrap: anywhere/)
})

test('relative news time stays readable and never emits invalid values', () => {
  const { formatRelativeTime } = require('../utils/format')
  const now = Date.parse('2026-08-09T04:00:00Z')
  assert.equal(formatRelativeTime('2026-08-09T03:59:40Z', now), '刚刚')
  assert.equal(formatRelativeTime('2026-08-09T03:55:00Z', now), '5分钟前')
  assert.equal(formatRelativeTime('2026-08-09T02:00:00Z', now), '2小时前')
  assert.equal(formatRelativeTime('invalid', now), '--')
})

test('fund formatting never turns unavailable NAV calculations into zero', () => {
  const { presentFund } = require('../utils/format')
  const fund = presentFund({
    code: '000001.OF',
    name: '仅持仓记录',
    official_nav: { value: null, source: 'Tushare', as_of: null, is_estimate: false, is_stale: false },
    intraday_estimate: { value: 1.2, source: '实验估值', as_of: null, is_estimate: true, is_stale: true },
    market_status: 'unavailable',
    holdings: [],
    position: {
      shares: 100,
      average_cost: 1,
      official_market_value: null,
      official_profit: null,
      official_profit_rate: null,
      estimated_market_value: null,
      estimated_profit: null,
      estimated_profit_rate: null
    }
  })
  assert.equal(fund.navText, '暂无数据')
  assert.equal(fund.estimateStaleText, '数据可能已过期')
  assert.equal(fund.position.officialMarketValueText, '--')
  assert.equal(fund.position.estimatedProfitText, '--')
  assert.equal(fund.position.estimateReliable, false)
})

test('closed-market presentation preserves the real timestamp and explains stale data', () => {
  const { presentQuote, presentFund } = require('../utils/format')
  const quote = presentQuote({
    symbol: 'sh000001',
    name: '上证指数',
    price: 3940.04,
    change: 39.68,
    change_percent: 1.02,
    timestamp: '2026-08-08T07:00:00Z',
    market_status: 'weekend',
    is_delayed: true,
    is_stale: true
  })
  assert.equal(quote.marketStatusText, '周末休市 · 最近交易日')
  assert.equal(quote.timestampText, '08-08 15:00')
  assert.match(quote.delayedText, /真实有效数据/)
  assert.equal(quote.marketStatusShortText, '周末休市')
  assert.equal(quote.timestampFullText, '2026-08-08 15:00')
  assert.equal(quote.priceLabel, '收盘')

  const fund = presentFund({
    market_status: 'closed',
    official_nav: { value: 1.2845, source: 'Tushare', as_of: '2026-08-08', is_estimate: false, is_stale: true },
    intraday_estimate: { value: 1.29, source: '实验估值', as_of: '2026-08-08T06:00:00Z', is_estimate: true, is_stale: true }
  })
  assert.equal(fund.navText, '1.2845')
  assert.equal(fund.officialLabelText, '正式净值')
  assert.equal(fund.estimateDisplayText, '休市')
  assert.equal(fund.estimateChangeDisplayText, '最近净值 08-08')
  assert.equal(fund.marketClosed, true)

  const published = presentFund({
    market_status: 'closed',
    official_nav: { value: 3.2692, source: '天天基金最新公布净值', as_of: '2026-08-10', is_estimate: false, is_stale: true },
    intraday_estimate: { value: 3.2746, source: '新浪财经实验性估值', as_of: '2026-08-10T08:04:00Z', is_estimate: true, is_stale: false }
  })
  assert.equal(published.officialLabelText, '最新公布净值')
  assert.equal(published.officialStaleText, '最近公布净值')
  assert.equal(published.estimateDisplayText, '休市')
})

test('finance chart exposes touch crosshair without adding chart dependencies', () => {
  const chartSource = fs.readFileSync(path.join(root, 'components/finance-chart/finance-chart.js'), 'utf8')
  const chartTemplate = fs.readFileSync(path.join(root, 'components/finance-chart/finance-chart.wxml'), 'utf8')
  assert.match(chartSource, /onTouchMove/)
  assert.match(chartSource, /drawCrosshair/)
  assert.match(chartTemplate, /tooltip\.open/)
  assert.doesNotMatch(chartSource, /echarts|@antv|f2-canvas/i)
})

test('AI assistant sends quick questions and renders structured real-data response', async () => {
  const context = createContext(loadPage('pages/ai/ai.js'))
  let request = null
  api.chatWithAI = async (message, conversation) => {
    request = { message, conversation }
    return {
      intent: 'NEWS_MARKET',
      answer: '最近交易日上证指数收涨，当前新闻提供了一项可能相关的政策因素。',
      summary: '行情上涨，原因仍需结合更多数据确认。',
      key_points: ['上证指数最近交易日上涨 1.02%'],
      market_impacts: ['政策变化可能改善市场预期'],
      references: [{ type: 'news', id: 'real-news', title: '真实中文新闻', source: '中新网财经' }],
      data_time: '2026-08-07T07:00:24Z',
      data_status: '行情为最近交易日数据，不是实时行情',
      disclaimer: '市场有风险，相关分析不构成投资建议。'
    }
  }
  await context.askQuickQuestion({ currentTarget: { dataset: { question: 'A股为什么涨？' } } })
  assert.deepEqual(request, { message: 'A股为什么涨？', conversation: [] })
  assert.equal(context.data.messages.length, 2)
  assert.equal(context.data.messages[1].response.intent, 'NEWS_MARKET')
  assert.equal(context.data.messages[1].response.intentText, '新闻与行情')
  assert.equal(context.data.messages[1].response.references[0].id, 'real-news')
  assert.equal(context.data.messages[1].response.showDataStatus, true)
  assert.equal(context.data.loading, false)
})

test('AI assistant supports input, bounded conversation, failure and retry', async () => {
  const context = createContext(loadPage('pages/ai/ai.js'))
  context.data.messages = Array.from({ length: 7 }, (_, index) => ({
    id: String(index),
    role: index % 2 ? 'assistant' : 'user',
    content: `question-${index}`,
    response: { answer: `answer-${index}` }
  }))
  let calls = 0
  let sentConversation = []
  api.chatWithAI = async (message, conversation) => {
    calls += 1
    sentConversation = conversation
    if (calls === 1) {
      const error = new Error('unavailable')
      error.statusCode = 503
      throw error
    }
    return {
      intent: 'FUND_ANALYSIS',
      answer: '当前暂无基金历史净值数据。',
      summary: '数据不足。',
      key_points: [],
      market_impacts: [],
      references: [],
      data_time: '2026-08-09T00:00:00Z',
      data_status: '历史净值数据源未授权',
      disclaimer: ''
    }
  }
  context.onInput({ detail: { value: '我的基金怎么样？' } })
  await context.sendMessage()
  assert.equal(sentConversation.length, 5)
  assert.match(context.data.errorMessage, /暂时不可用/)
  await context.retry()
  assert.equal(calls, 2)
  assert.equal(context.data.errorMessage, '')
  assert.equal(context.data.messages.at(-1).response.data_status, '历史净值数据源未授权')
})

test('AI assistant distinguishes timeout from a stopped local service', async () => {
  const context = createContext(loadPage('pages/ai/ai.js'))
  api.chatWithAI = async () => {
    const error = new Error('request:fail timeout')
    error.code = 'TIMEOUT'
    throw error
  }
  await context.ask('今日市场')
  assert.match(context.data.errorMessage, /分析超时/)

  api.chatWithAI = async () => {
    const error = new Error('request:fail connection refused')
    error.code = 'NETWORK_ERROR'
    throw error
  }
  await context.ask('重要新闻')
  assert.match(context.data.errorMessage, /本地服务已启动/)
})

test('AI references navigate only to real product detail pages', () => {
  const context = createContext(loadPage('pages/ai/ai.js'))
  let url = ''
  global.wx.navigateTo = (value) => { url = value.url }
  context.openReference({ currentTarget: { dataset: { type: 'news', id: 'news-id' } } })
  assert.equal(url, '/pages/news-detail/news-detail?id=news-id')
  context.openReference({ currentTarget: { dataset: { type: 'event', id: 'event-id' } } })
  assert.equal(url, '/pages/news-detail/news-detail?id=news-id')
  const template = fs.readFileSync(path.join(root, 'pages/ai/ai.wxml'), 'utf8')
  assert.match(template, /scroll-view/)
  assert.match(template, /正在检索财经数据/)
  assert.doesNotMatch(template, /正在完善中|即将上线/)
  const configSource = fs.readFileSync(path.join(root, 'config.js'), 'utf8')
  const apiSource = fs.readFileSync(path.join(root, 'services/api.js'), 'utf8')
  assert.match(configSource, /AI_REQUEST_TIMEOUT: 70000/)
  assert.match(configSource, /REQUEST_TIMEOUT: 30000/)
  assert.match(apiSource, /AI_REQUEST_TIMEOUT/)
})
