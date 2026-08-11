function formatDate(value) {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '--'
  const pad = (number) => String(number).padStart(2, '0')
  const shanghai = new Date(date.getTime() + 8 * 60 * 60 * 1000)
  const now = new Date(Date.now() + 8 * 60 * 60 * 1000)
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate())
  const target = Date.UTC(
    shanghai.getUTCFullYear(),
    shanghai.getUTCMonth(),
    shanghai.getUTCDate()
  )
  const time = `${pad(shanghai.getUTCHours())}:${pad(shanghai.getUTCMinutes())}`
  if (target === today) return `今天 ${time}`
  if (target === today - 24 * 60 * 60 * 1000) return `昨天 ${time}`
  return `${shanghai.getUTCFullYear()}年${shanghai.getUTCMonth() + 1}月${shanghai.getUTCDate()}日 ${time}`
}

function formatClock(value) {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '--'
  const pad = (number) => String(number).padStart(2, '0')
  const shanghai = new Date(date.getTime() + 8 * 60 * 60 * 1000)
  return `${pad(shanghai.getUTCHours())}:${pad(shanghai.getUTCMinutes())}:${pad(shanghai.getUTCSeconds())}`
}

function formatDataTimestamp(value) {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '--'
  const pad = (number) => String(number).padStart(2, '0')
  const shanghai = new Date(date.getTime() + 8 * 60 * 60 * 1000)
  return `${pad(shanghai.getUTCMonth() + 1)}-${pad(shanghai.getUTCDate())} ${pad(shanghai.getUTCHours())}:${pad(shanghai.getUTCMinutes())}`
}

function formatFullDataTimestamp(value) {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '--'
  const pad = (number) => String(number).padStart(2, '0')
  const shanghai = new Date(date.getTime() + 8 * 60 * 60 * 1000)
  return `${shanghai.getUTCFullYear()}-${pad(shanghai.getUTCMonth() + 1)}-${pad(shanghai.getUTCDate())} ${pad(shanghai.getUTCHours())}:${pad(shanghai.getUTCMinutes())}`
}

function formatRelativeTime(value, nowValue = Date.now()) {
  if (!value) return '--'
  const timestamp = new Date(value).getTime()
  if (!Number.isFinite(timestamp)) return '--'
  const difference = Math.max(0, nowValue - timestamp)
  if (difference < 60 * 1000) return '刚刚'
  if (difference < 60 * 60 * 1000) return `${Math.floor(difference / 60000)}分钟前`
  if (difference < 24 * 60 * 60 * 1000) return `${Math.floor(difference / 3600000)}小时前`
  return formatDate(value)
}

function formatHomeDate(nowValue = Date.now()) {
  const date = new Date(nowValue + 8 * 60 * 60 * 1000)
  const weekdays = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六']
  const month = String(date.getUTCMonth() + 1).padStart(2, '0')
  const day = String(date.getUTCDate()).padStart(2, '0')
  return `${month}月${day}日 · ${weekdays[date.getUTCDay()]}`
}

function stars(value) {
  const count = Math.max(0, Math.min(5, Number(value) || 0))
  return '★'.repeat(count)
}

function presentNews(item) {
  return {
    ...item,
    isImportant: Number(item.importance) >= 4,
    publishedAtText: formatDate(item.published_at),
    publishedRelativeText: formatRelativeTime(item.published_at),
    importanceText: stars(item.importance),
    categoryText: localizeCategory(item.category)
  }
}

const MARKET_STATUS = {
  trading: '交易中',
  closed: '已收盘',
  weekend: '周末休市 · 最近交易日',
  holiday: '节假日休市 · 最近交易日',
  pre_market: '盘前',
  post_market: '盘后',
  unavailable: '暂无数据'
}

const MARKET_STATUS_SHORT = {
  trading: '交易中',
  closed: '已收盘',
  weekend: '周末休市',
  holiday: '节假日休市',
  pre_market: '盘前',
  post_market: '盘后',
  unavailable: '暂无数据'
}

const CLOSED_MARKET_STATUS = new Set(['closed', 'weekend', 'holiday'])

const DIRECTION = {
  bullish: '看涨',
  bearish: '看跌',
  neutral: '中性'
}

const CATEGORY = {
  macro: '宏观经济',
  company: '公司动态',
  policy: '政策',
  market: '市场',
  commodity: '大宗商品',
  forex: '外汇',
  geopolitics: '地缘政治'
}

const ASSET = {
  gold: '黄金',
  oil: '原油',
  crude_oil: '原油',
  usd: '美元',
  dollar: '美元',
  a_share: 'A股',
  hk_stock: '港股',
  us_stock: '美股',
  bond: '债券'
}

function signed(value, suffix = '') {
  if (value === null || value === undefined || value === '') return '--'
  const number = Number(value)
  if (!Number.isFinite(number)) return '--'
  const prefix = number > 0 ? '+' : ''
  return `${prefix}${number.toFixed(2)}${suffix}`
}

function presentQuote(item) {
  const available = item.price !== null && item.price !== undefined && Number.isFinite(Number(item.price))
  const change = Number(item.change)
  const isClosedMarket = CLOSED_MARKET_STATUS.has(item.market_status)
  const isStale = Boolean(item.is_stale)
  return {
    ...item,
    available,
    priceText: available ? Number(item.price).toFixed(2) : '暂无数据',
    changeText: available ? signed(item.change) : '--',
    changePercentText: available ? signed(item.change_percent, '%') : '--',
    changeClass: !available || change === 0 ? 'flat' : change > 0 ? 'rise' : 'fall',
    marketStatusText: MARKET_STATUS[item.market_status] || '暂无数据',
    marketStatusShortText: MARKET_STATUS_SHORT[item.market_status] || '暂无数据',
    timestampText: formatDataTimestamp(item.timestamp),
    timestampFullText: formatFullDataTimestamp(item.timestamp),
    directionText: DIRECTION[item.direction] || item.direction,
    delayedText: isStale
      ? isClosedMarket ? '休市期间展示最近真实有效数据' : '数据源暂时不可用，已显示最近有效数据'
      : item.is_delayed ? '数据可能已延迟' : '',
    dataTimeLabel: item.market_status === 'trading' ? '更新于' : isClosedMarket ? '最近交易日' : '数据截至',
    priceLabel: item.market_status === 'trading' ? '现价' : isClosedMarket ? '收盘' : '价格',
    isClosedMarket,
    isStale
  }
}

const FUND_STATUS = {
  trading: '交易时段',
  closed: '休市，展示最近正式净值',
  weekend: '周末休市，展示最近正式净值',
  holiday: '节假日休市，展示最近正式净值',
  unavailable: '暂无数据'
}

function formatDateOnly(value) {
  if (!value) return '--'
  const parts = String(value).split('-')
  if (parts.length !== 3) return '--'
  return `${parts[0]}年${Number(parts[1])}月${Number(parts[2])}日`
}

function money(value) {
  if (value === null || value === undefined || value === '') return '--'
  const number = Number(value)
  return Number.isFinite(number) ? number.toFixed(2) : '--'
}

function presentFund(item) {
  const official = item.official_nav || {
    value: item.latest_nav,
    source: item.source,
    as_of: item.nav_date,
    is_estimate: false,
    is_stale: false
  }
  const estimate = item.intraday_estimate || {
    value: null,
    source: '天天基金实验性估值',
    as_of: null,
    is_estimate: true,
    is_stale: true
  }
  const navAvailable = official.value !== null && official.value !== undefined && Number.isFinite(Number(official.value))
  const estimateAvailable = estimate.value !== null && estimate.value !== undefined && Number.isFinite(Number(estimate.value))
  const officialIsTushare = String(official.source || '').toLowerCase().includes('tushare')
  const officialLabelText = officialIsTushare ? '正式净值' : '最新公布净值'
  const marketClosed = CLOSED_MARKET_STATUS.has(item.market_status)
  const estimateReliable = estimateAvailable && !estimate.is_stale && !marketClosed
  const position = item.position
    ? {
        ...item.position,
        sharesText: Number(item.position.shares).toFixed(2),
        averageCostText: Number(item.position.average_cost).toFixed(4),
        officialMarketValueText: money(item.position.official_market_value),
        officialProfitText: signed(item.position.official_profit),
        officialProfitRateText: signed(item.position.official_profit_rate, '%'),
        officialProfitClass: valueClass(item.position.official_profit),
        estimatedMarketValueText: money(item.position.estimated_market_value),
        estimatedProfitText: signed(item.position.estimated_profit),
        estimatedProfitRateText: signed(item.position.estimated_profit_rate, '%'),
        estimatedProfitClass: valueClass(item.position.estimated_profit),
        estimateReliable: item.position.estimated_market_value !== null && item.position.estimated_market_value !== undefined
      }
    : null
  const preferredProfit = position
    ? estimateReliable && position.estimateReliable
      ? {
          text: position.estimatedProfitText,
          rate: position.estimatedProfitRateText,
          className: position.estimatedProfitClass,
          label: '估算持仓收益'
        }
      : {
          text: position.officialProfitText,
          rate: position.officialProfitRateText,
          className: position.officialProfitClass,
          label: '正式持仓收益'
        }
    : null
  return {
    ...item,
    navAvailable,
    officialLabelText,
    navText: navAvailable ? Number(official.value).toFixed(4) : '暂无数据',
    navDateText: formatFundAsOf(official.as_of),
    navDateCompactText: official.as_of ? String(official.as_of).slice(5, 10) : '--',
    officialStaleText: official.is_stale && navAvailable
      ? officialIsTushare ? '最近正式净值' : '最近公布净值'
      : '',
    officialSourceText: official.source || item.source || '暂无数据',
    estimateAvailable,
    estimateReliable,
    estimateText: estimateAvailable ? Number(estimate.value).toFixed(4) : '暂无可靠数据',
    estimateDisplayText: estimateReliable
      ? Number(estimate.value).toFixed(4)
      : marketClosed ? '休市' : '暂无可靠数据',
    estimateChangeText: estimateAvailable ? signed(item.estimate_change_percent, '%') : '--',
    estimateChangeDisplayText: estimateReliable ? signed(item.estimate_change_percent, '%') : `最近净值 ${official.as_of ? String(official.as_of).slice(5, 10) : '--'}`,
    estimateChangeClass: valueClass(item.estimate_change_percent),
    estimateTimeText: formatDate(estimate.as_of),
    estimateSourceText: estimate.source || '暂无数据',
    estimateSourceTimeText: estimateAvailable
      ? `${estimate.source || '实验性估值'} · ${formatDate(estimate.as_of)}`
      : '暂无可靠估值',
    estimateStaleText: !marketClosed && estimate.is_stale && estimateAvailable ? '数据可能已过期' : '',
    estimateStatusText: estimateReliable
      ? '实验性盘中估值'
      : marketClosed ? '盘中估算：休市' : '盘中估值：暂无可靠数据',
    holdingsReportDateText: formatDateOnly(item.holdings_report_date),
    marketStatusText: FUND_STATUS[item.market_status] || '暂无数据',
    marketClosed,
    preferredProfit,
    position,
    holdings: (item.holdings || []).map((holding) => ({
      ...holding,
      weightText: holding.weight_percent !== null && holding.weight_percent !== undefined && Number.isFinite(Number(holding.weight_percent)) ? `${Number(holding.weight_percent).toFixed(2)}%` : '--',
      changeText: holding.change_percent !== null && holding.change_percent !== undefined && Number.isFinite(Number(holding.change_percent)) ? signed(holding.change_percent, '%') : '暂无行情',
      changeClass: valueClass(holding.change_percent),
      reportDateText: formatDateOnly(holding.report_date)
    }))
  }
}

function valueClass(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return 'flat'
  return Number(value) > 0 ? 'rise' : Number(value) < 0 ? 'fall' : 'flat'
}

function formatFundAsOf(value) {
  if (!value) return '--'
  return String(value).includes('T') ? formatDate(value) : formatDateOnly(value)
}

function localizeDirection(value) {
  return DIRECTION[value] || value || '--'
}

function localizeCategory(value) {
  return CATEGORY[value] || value || '未分类'
}

function localizeAsset(value) {
  return ASSET[value] || value || '相关资产'
}

function formatConfidence(value) {
  const number = Number(value)
  return Number.isFinite(number) ? `${Math.round(number * 100)}%` : '--'
}

module.exports = {
  formatDate,
  formatClock,
  formatDataTimestamp,
  formatFullDataTimestamp,
  formatRelativeTime,
  formatHomeDate,
  stars,
  presentNews,
  presentQuote,
  presentFund,
  formatDateOnly,
  localizeDirection,
  localizeCategory,
  localizeAsset,
  formatConfidence
}
