const api = require('../../services/api')
const { formatClock, formatHomeDate, presentFund, presentNews, presentQuote } = require('../../utils/format')

const HOME_MARKET_SYMBOLS = ['sh000001', 'sz399001', 'hk_hsi']

Page({
  data: {
    status: 'loading',
    dateText: '',
    featuredNews: null,
    newsItems: [],
    marketItems: [],
    primaryMarket: null,
    secondaryMarkets: [],
    fundItems: [],
    trend: null,
    newsSourceStatus: '',
    generatedAt: '--'
  },

  onLoad() {
    this.setData({ dateText: formatHomeDate() })
    this.loadDashboard()
  },

  onShow() {
    if (this.hasLoaded) this.loadDashboard(false, true)
  },

  onPullDownRefresh() {
    this.loadDashboard(true)
  },

  retry() {
    this.loadDashboard()
  },

  async loadDashboard(fromRefresh = false, silent = false) {
    if (!fromRefresh && !silent) this.setData({ status: 'loading' })
    const [dashboard, market, funds, history] = await Promise.all([
      api.getDashboard().catch(() => null),
      api.getMarket().catch(() => null),
      api.getFundWatchlist(false).catch(() => null),
      api.getMarketHistory('sh000001', 'day', '1m').catch(() => null)
    ])
    try {
      if (!dashboard && !market && !funds) throw new Error('dashboard unavailable')
      const news = dashboard ? (dashboard.top_news || []).map(presentNews) : []
      const marketItems = market
        ? (market.items || []).filter((item) => HOME_MARKET_SYMBOLS.includes(item.symbol)).map(presentQuote)
        : []
      const primaryMarket = marketItems.find((item) => item.symbol === 'sh000001') || marketItems[0] || null
      const fundItems = funds ? (funds.items || []).slice(0, 2).map(presentFund) : []
      const trendItems = history && history.status === 'available' ? history.items || [] : []
      const trendDirection = trendItems.length > 1
        ? Number(trendItems[trendItems.length - 1].close) > Number(trendItems[0].close) ? 'rise'
          : Number(trendItems[trendItems.length - 1].close) < Number(trendItems[0].close) ? 'fall' : 'flat'
        : 'flat'
      this.hasLoaded = true
      this.setData({
        status: 'success',
        dateText: formatHomeDate(),
        featuredNews: news[0] || null,
        newsItems: news.slice(1, 5),
        marketItems,
        primaryMarket,
        secondaryMarkets: marketItems.filter((item) => !primaryMarket || item.symbol !== primaryMarket.symbol),
        fundItems,
        trend: trendItems.length ? { items: trendItems, direction: trendDirection } : null,
        newsSourceStatus: dashboard && dashboard.system_status !== '正常' ? dashboard.system_status : '',
        generatedAt: formatClock((dashboard && dashboard.generated_at) || (market && market.generated_at))
      })
    } catch (error) {
      if (!silent) this.setData({ status: 'error' })
    } finally {
      if (fromRefresh) wx.stopPullDownRefresh()
    }
  },

  openNews(event) {
    wx.navigateTo({ url: `/pages/news-detail/news-detail?id=${event.currentTarget.dataset.id}` })
  },

  openMarket(event) {
    wx.navigateTo({ url: `/pages/market-detail/market-detail?symbol=${event.currentTarget.dataset.symbol}` })
  },

  openFund(event) {
    wx.navigateTo({ url: `/pages/fund-detail/fund-detail?code=${encodeURIComponent(event.currentTarget.dataset.code)}` })
  }
})
