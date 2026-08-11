const api = require('../../services/api')
const { presentFund } = require('../../utils/format')

const AUTO_REFRESH_MS = 30000

Page({
  data: {
    code: '',
    status: 'loading',
    fund: null,
    sharesInput: '',
    averageCostInput: '',
    refreshing: false,
    saving: false,
    navHistoryStatus: 'loading',
    navHistory: null,
    navRange: '3m',
    navRangeOptions: [
      { value: '1m', label: '1月' },
      { value: '3m', label: '3月' },
      { value: '6m', label: '6月' },
      { value: '1y', label: '1年' }
    ]
  },

  onLoad(options) {
    if (!options.code) {
      this.setData({ status: 'error' })
      return
    }
    this.setData({ code: decodeURIComponent(options.code) })
    this.loadFund()
    this.loadNavHistory()
  },

  onShow() {
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
    this.autoRefreshTimer = setInterval(() => this.loadFund({ silent: true }), AUTO_REFRESH_MS)
  },

  stopAutoRefresh() {
    if (this.autoRefreshTimer) clearInterval(this.autoRefreshTimer)
    this.autoRefreshTimer = null
  },

  onPullDownRefresh() {
    Promise.all([
      this.loadFund({ refresh: true }),
      this.loadNavHistory(true)
    ]).finally(() => wx.stopPullDownRefresh())
  },

  retry() {
    this.loadFund()
  },

  manualRefresh() {
    this.loadFund({ refresh: true, manual: true })
    this.loadNavHistory(true)
  },

  selectNavRange(event) {
    this.setData({ navRange: event.currentTarget.dataset.value })
    this.loadNavHistory()
  },

  retryNavHistory() {
    this.loadNavHistory()
  },

  async loadNavHistory(refresh = false) {
    this.setData({ navHistoryStatus: 'loading' })
    try {
      const result = await api.getFundNavHistory(this.data.code, this.data.navRange, refresh)
      const available = result.status === 'available' && Array.isArray(result.items) && result.items.length > 0
      this.setData({
        navHistoryStatus: available ? 'success' : result.status,
        navHistory: {
          ...result,
          asOfText: result.as_of || '--',
          stateText: result.message || '暂无历史净值数据'
        }
      })
    } catch (error) {
      this.setData({ navHistoryStatus: 'error', navHistory: null })
    }
  },

  onSharesInput(event) {
    this.setData({ sharesInput: event.detail.value })
  },

  onCostInput(event) {
    this.setData({ averageCostInput: event.detail.value })
  },

  async loadFund(options = {}) {
    const { refresh = false, fromPullDown = false, manual = false, silent = false } = options
    if (!fromPullDown && !manual && !silent) this.setData({ status: 'loading' })
    if (manual) this.setData({ refreshing: true })
    try {
      const result = presentFund(await api.getFundDetail(this.data.code, refresh))
      this.setData({
        status: 'success',
        fund: result,
        sharesInput: result.position ? String(result.position.shares) : '',
        averageCostInput: result.position ? String(result.position.average_cost) : ''
      })
      wx.setNavigationBarTitle({ title: result.name || '基金详情' })
      if (manual) wx.showToast({ title: '刷新完成', icon: 'success' })
    } catch (error) {
      if (!silent) this.setData({ status: 'error' })
      if (manual) wx.showToast({ title: '基金数据暂不可用', icon: 'none' })
    } finally {
      this.setData({ refreshing: false })
      if (fromPullDown) wx.stopPullDownRefresh()
    }
  },

  async toggleFavorite() {
    try {
      if (this.data.fund.is_favorite) {
        await api.removeFundWatchlist(this.data.code)
        this.setData({ 'fund.is_favorite': false })
        wx.showToast({ title: '已移除自选', icon: 'success' })
      } else {
        await api.addFundWatchlist(this.data.code)
        this.setData({ 'fund.is_favorite': true })
        wx.showToast({ title: '已加入自选', icon: 'success' })
      }
    } catch (error) {
      wx.showToast({ title: '操作失败，请重试', icon: 'none' })
    }
  },

  async savePosition() {
    const shares = Number(this.data.sharesInput)
    const averageCost = Number(this.data.averageCostInput)
    if (!Number.isFinite(shares) || shares <= 0) {
      wx.showToast({ title: '请输入有效的持有份额', icon: 'none' })
      return
    }
    if (!Number.isFinite(averageCost) || averageCost < 0) {
      wx.showToast({ title: '请输入有效的平均成本', icon: 'none' })
      return
    }
    this.setData({ saving: true })
    try {
      await api.saveFundPosition(this.data.code, { shares, average_cost: averageCost })
      await this.loadFund()
      wx.showToast({ title: '持仓已保存', icon: 'success' })
    } catch (error) {
      wx.showToast({ title: '保存失败，请重试', icon: 'none' })
    } finally {
      this.setData({ saving: false })
    }
  },

  removePosition() {
    wx.showModal({
      title: '删除持仓',
      content: '确认删除这只基金的持仓记录？',
      success: async (result) => {
        if (!result.confirm) return
        try {
          await api.removeFundPosition(this.data.code)
          await this.loadFund()
          wx.showToast({ title: '持仓已删除', icon: 'success' })
        } catch (error) {
          wx.showToast({ title: '删除失败，请重试', icon: 'none' })
        }
      }
    })
  }
})
