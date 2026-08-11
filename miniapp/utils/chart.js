function finite(value) {
  if (value === null || value === undefined || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function normalizeMarketPoints(items) {
  return (Array.isArray(items) ? items : [])
    .map((item) => ({
      timestamp: item.timestamp,
      open: finite(item.open),
      high: finite(item.high),
      low: finite(item.low),
      close: finite(item.close),
      volume: finite(item.volume),
      ma5: finite(item.ma5),
      ma10: finite(item.ma10),
      ma20: finite(item.ma20),
      ma60: finite(item.ma60)
    }))
    .filter((item) => item.timestamp && [item.open, item.high, item.low, item.close].every((value) => value !== null))
    .sort((left, right) => new Date(left.timestamp) - new Date(right.timestamp))
}

function normalizeNavPoints(items) {
  return (Array.isArray(items) ? items : [])
    .map((item) => ({
      timestamp: item.nav_date,
      value: finite(item.adj_nav) !== null ? finite(item.adj_nav) : finite(item.unit_nav)
    }))
    .filter((item) => item.timestamp && item.value !== null)
    .sort((left, right) => new Date(left.timestamp) - new Date(right.timestamp))
}

function bounds(values) {
  const valid = values.filter((value) => Number.isFinite(value))
  if (!valid.length) return null
  let min = Math.min(...valid)
  let max = Math.max(...valid)
  if (min === max) {
    const padding = Math.abs(min) * 0.01 || 1
    min -= padding
    max += padding
  }
  return { min, max }
}

module.exports = { bounds, normalizeMarketPoints, normalizeNavPoints }
