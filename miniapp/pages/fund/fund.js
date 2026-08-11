const api = require('../../services/api')
const { formatClock, presentFund } = require('../../utils/format')

const AUTO_REFRESH_MS = 30000

Page({
  data: {
    status: 'loading',
    items: [],
    query: '',
    searchStatus: 'idle',
    searchItems: [],
    providerMessage: '',
    lastUpdated: '--',
    refreshing: false
  },

  onLoad() {
    this.loadWatchlist()
  },

  onShow() {
    if (this.hasLoaded) this.loadWatchlist({ silent: true })
    this.startAutoRefresh()
  },

  onHide() {
    this.stopAutoRefresh()
  },

  onUnload() {
    this.stopAutoRefresh()
  },

  startAutoRefresh() {
    this.stopAutoRefresh()
    this.autoRefreshTimer = setInterval(() => {
      this.loadWatchlist({ silent: true })
    }, AUTO_REFRESH_MS)
  },

  stopAutoRefresh() {
    if (this.autoRefreshTimer) clearInterval(this.autoRefreshTimer)
    this.autoRefreshTimer = null
  },

  onPullDownRefresh() {
    this.loadWatchlist({ refresh: true, fromPullDown: true })
  },

  onQueryInput(event) {
    this.setData({ query: event.detail.value })
  },

  async search() {
    const query = this.data.query.trim()
    if (!query) {
      wx.showToast({ title: '请输入基金代码或名称', icon: 'none' })
      return
    }
    this.setData({ searchStatus: 'loading' })
    try {
      const result = await api.searchFunds(query)
      this.setData({
        searchStatus: result.items && result.items.length ? 'success' : 'empty',
        searchItems: result.items || [],
        providerMessage: result.message || this.data.providerMessage
      })
    } catch (error) {
      this.setData({ searchStatus: 'error', searchItems: [] })
    }
  },

  manualRefresh() {
    this.loadWatchlist({ refresh: true, manual: true })
  },

  retry() {
    this.loadWatchlist()
  },

  async loadWatchlist(options = {}) {
    const { refresh = false, fromPullDown = false, manual = false, silent = false } = options
    if (!silent && !fromPullDown && !manual) this.setData({ status: 'loading' })
    if (manual) this.setData({ refreshing: true })
    try {
      const result = await api.getFundWatchlist(refresh)
      const items = (result.items || []).map(presentFund)
      this.hasLoaded = true
      this.setData({
        status: items.length ? 'success' : 'empty',
        items,
        providerMessage: result.message || '',
        lastUpdated: formatClock(result.generated_at)
      })
      if (manual) wx.showToast({ title: '刷新完成', icon: 'success' })
    } catch (error) {
      if (!silent) this.setData({ status: 'error' })
      if (manual) wx.showToast({ title: '基金数据暂不可用', icon: 'none' })
    } finally {
      this.setData({ refreshing: false })
      if (fromPullDown) wx.stopPullDownRefresh()
    }
  },

  async addFund(event) {
    const { code } = event.currentTarget.dataset
    try {
      await api.addFundWatchlist(code)
      wx.showToast({ title: '已加入自选', icon: 'success' })
      await this.loadWatchlist({ silent: true })
    } catch (error) {
      wx.showToast({ title: '添加失败，请重试', icon: 'none' })
    }
  },

  removeFund(event) {
    const { code } = event.currentTarget.dataset
    wx.showModal({
      title: '移除自选',
      content: '确认从自选基金中移除？持仓记录不会被删除。',
      success: async (result) => {
        if (!result.confirm) return
        try {
          await api.removeFundWatchlist(code)
          await this.loadWatchlist({ silent: true })
        } catch (error) {
          wx.showToast({ title: '移除失败，请重试', icon: 'none' })
        }
      }
    })
  },

  openDetail(event) {
    const { code } = event.currentTarget.dataset
    wx.navigateTo({ url: `/pages/fund-detail/fund-detail?code=${encodeURIComponent(code)}` })
  }
})
