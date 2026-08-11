const api = require('../../services/api')
const { formatClock, presentQuote } = require('../../utils/format')

const REFRESH_INTERVAL = 60 * 1000
const GROUPS = [
  { key: 'CN', title: 'A股' },
  { key: 'US', title: '美股' },
  { key: 'HK', title: '港股' },
  { key: 'COMMODITY', title: '大宗商品' },
  { key: 'FX', title: '外汇' }
]

Page({
  data: {
    status: 'loading',
    groups: [],
    visibleItems: [],
    activeGroup: 'CN',
    lastUpdated: '--',
    refreshing: false,
    hasDelayedData: false,
    hasStaleData: false,
    hasClosedData: false
  },

  onLoad() {
    this.loadMarket()
  },

  onShow() {
    this.startRefreshTimer()
  },

  onHide() {
    this.stopRefreshTimer()
  },

  onUnload() {
    this.stopRefreshTimer()
  },

  onPullDownRefresh() {
    this.loadMarket({ fromPullDown: true })
  },

  retry() {
    this.loadMarket()
  },

  manualRefresh() {
    this.loadMarket({ manual: true })
  },

  async loadMarket(options = {}) {
    const { fromPullDown = false, manual = false, silent = false } = options
    if (!silent && !fromPullDown && !manual) this.setData({ status: 'loading' })
    if (manual) this.setData({ refreshing: true })
    try {
      const result = await api.getMarket()
      const quotes = (result.items || []).map(presentQuote)
      const groups = GROUPS.map((group) => ({
        ...group,
        items: quotes.filter((item) => item.market === group.key)
      })).filter((group) => group.items.length)
      const activeGroup = groups.some((group) => group.key === this.data.activeGroup)
        ? this.data.activeGroup
        : groups.length ? groups[0].key : 'CN'
      this.setData({
        status: quotes.length ? 'success' : 'empty',
        groups,
        activeGroup,
        visibleItems: (groups.find((group) => group.key === activeGroup) || { items: [] }).items,
        lastUpdated: formatClock(result.generated_at),
        hasDelayedData: quotes.some((item) => item.is_delayed),
        hasStaleData: quotes.some((item) => item.isStale && !item.isClosedMarket),
        hasClosedData: quotes.some((item) => item.available && item.isClosedMarket)
      })
      if (manual) wx.showToast({ title: '刷新成功', icon: 'success' })
    } catch (error) {
      if (!silent) this.setData({ status: 'error' })
      if (manual || silent) wx.showToast({ title: '行情暂不可用', icon: 'none' })
    } finally {
      this.setData({ refreshing: false })
      if (fromPullDown) wx.stopPullDownRefresh()
    }
  },

  selectGroup(event) {
    const activeGroup = event.currentTarget.dataset.key
    const group = this.data.groups.find((item) => item.key === activeGroup)
    this.setData({ activeGroup, visibleItems: group ? group.items : [] })
  },

  startRefreshTimer() {
    this.stopRefreshTimer()
    this.refreshTimer = setInterval(() => this.loadMarket({ silent: true }), REFRESH_INTERVAL)
  },

  stopRefreshTimer() {
    if (this.refreshTimer) {
      clearInterval(this.refreshTimer)
      this.refreshTimer = null
    }
  },

  openDetail(event) {
    const { symbol } = event.currentTarget.dataset
    wx.navigateTo({ url: `/pages/market-detail/market-detail?symbol=${symbol}` })
  }
})
