const api = require('../../services/api')
const { presentQuote } = require('../../utils/format')

Page({
  data: {
    symbol: '',
    status: 'loading',
    quote: null,
    refreshing: false,
    historyStatus: 'loading',
    history: null,
    selectedPeriod: 'day',
    selectedRange: '1m',
    periodOptions: [
      { value: 'intraday', label: '分时' },
      { value: 'day', label: '日K' },
      { value: 'week', label: '周K' },
      { value: 'month', label: '月K' }
    ],
    rangeOptions: [
      { value: '1m', label: '1月' },
      { value: '3m', label: '3月' },
      { value: '6m', label: '6月' },
      { value: '1y', label: '1年' },
      { value: '5y', label: '5年' }
    ]
  },

  onLoad(options) {
    if (!options.symbol) {
      this.setData({ status: 'error' })
      return
    }
    this.setData({ symbol: options.symbol })
    this.loadAll()
  },

  onPullDownRefresh() {
    this.loadAll(true)
  },

  retry() {
    this.loadAll()
  },

  manualRefresh() {
    this.loadAll(false, true)
  },

  async loadAll(fromPullDown = false, manual = false) {
    if (manual) this.setData({ refreshing: true })
    await Promise.all([this.loadQuote(false), this.loadHistory()])
    if (manual) {
      this.setData({ refreshing: false })
      wx.showToast({ title: '刷新完成', icon: 'success' })
    }
    if (fromPullDown) wx.stopPullDownRefresh()
  },

  selectPeriod(event) {
    const period = event.currentTarget.dataset.value
    const range = period === 'intraday' ? '1d' : period === 'month' ? '1y' : '1m'
    this.setData({ selectedPeriod: period, selectedRange: range })
    this.loadHistory()
  },

  selectRange(event) {
    this.setData({ selectedRange: event.currentTarget.dataset.value })
    this.loadHistory()
  },

  refreshHistory() {
    this.loadHistory()
  },

  async loadHistory() {
    this.setData({ historyStatus: 'loading' })
    try {
      const result = await api.getMarketHistory(
        this.data.symbol,
        this.data.selectedPeriod,
        this.data.selectedRange
      )
      const available = result.status === 'available' && Array.isArray(result.items) && result.items.length > 0
      this.setData({
        historyStatus: available ? 'success' : result.status,
        history: {
          ...result,
          chartMode: this.data.selectedPeriod === 'intraday' ? 'line' : 'candlestick',
          asOfText: result.as_of ? String(result.as_of).replace('T', ' ').slice(0, 16) : '--',
          stateText: result.message || '暂无历史行情数据'
        }
      })
    } catch (error) {
      this.setData({ historyStatus: 'error', history: null })
    }
  },

  async loadQuote(fromPullDown = false) {
    if (!fromPullDown) this.setData({ status: 'loading' })
    try {
      const result = await api.getMarketDetail(this.data.symbol)
      this.setData({ status: 'success', quote: presentQuote(result) })
      wx.setNavigationBarTitle({ title: result.name || '行情详情' })
    } catch (error) {
      this.setData({ status: 'error' })
    } finally {
      if (fromPullDown) wx.stopPullDownRefresh()
    }
  }
})
