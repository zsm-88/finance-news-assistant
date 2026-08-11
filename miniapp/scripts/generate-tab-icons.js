const fs = require('node:fs')
const path = require('node:path')
const zlib = require('node:zlib')

const SIZE = 81
const COLORS = { normal: [115, 129, 152, 255], active: [48, 199, 232, 255] }

function crc32(buffer) {
  let crc = 0xffffffff
  for (const byte of buffer) {
    crc ^= byte
    for (let bit = 0; bit < 8; bit += 1) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1))
  }
  return (crc ^ 0xffffffff) >>> 0
}

function chunk(type, data) {
  const name = Buffer.from(type)
  const length = Buffer.alloc(4)
  length.writeUInt32BE(data.length)
  const crc = Buffer.alloc(4)
  crc.writeUInt32BE(crc32(Buffer.concat([name, data])))
  return Buffer.concat([length, name, data, crc])
}

function canvas() {
  return new Uint8Array(SIZE * SIZE * 4)
}

function pixel(data, x, y, color) {
  x = Math.round(x); y = Math.round(y)
  if (x < 0 || y < 0 || x >= SIZE || y >= SIZE) return
  const offset = (y * SIZE + x) * 4
  data.set(color, offset)
}

function disc(data, x, y, radius, color) {
  for (let yy = -radius; yy <= radius; yy += 1) {
    for (let xx = -radius; xx <= radius; xx += 1) {
      if (xx * xx + yy * yy <= radius * radius) pixel(data, x + xx, y + yy, color)
    }
  }
}

function line(data, x1, y1, x2, y2, color, width = 4) {
  const steps = Math.max(Math.abs(x2 - x1), Math.abs(y2 - y1)) * 2
  for (let index = 0; index <= steps; index += 1) {
    const ratio = steps ? index / steps : 0
    disc(data, x1 + (x2 - x1) * ratio, y1 + (y2 - y1) * ratio, width / 2, color)
  }
}

function circle(data, cx, cy, radius, color, width = 4) {
  for (let degree = 0; degree < 360; degree += 1) {
    const angle = degree * Math.PI / 180
    disc(data, cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius, width / 2, color)
  }
}

function rect(data, x, y, width, height, color, stroke = 4) {
  line(data, x, y, x + width, y, color, stroke)
  line(data, x + width, y, x + width, y + height, color, stroke)
  line(data, x + width, y + height, x, y + height, color, stroke)
  line(data, x, y + height, x, y, color, stroke)
}

const icons = {
  home(data, color) {
    line(data, 16, 39, 40, 17, color); line(data, 40, 17, 65, 39, color)
    line(data, 22, 35, 22, 65, color); line(data, 59, 35, 59, 65, color)
    line(data, 22, 65, 59, 65, color); rect(data, 34, 47, 13, 18, color, 3)
  },
  news(data, color) {
    rect(data, 19, 14, 43, 53, color); line(data, 28, 28, 53, 28, color, 3)
    line(data, 28, 39, 53, 39, color, 3); line(data, 28, 50, 47, 50, color, 3)
  },
  market(data, color) {
    line(data, 17, 63, 17, 19, color, 3); line(data, 17, 63, 66, 63, color, 3)
    line(data, 23, 53, 34, 40, color); line(data, 34, 40, 44, 47, color); line(data, 44, 47, 62, 25, color)
    line(data, 52, 25, 62, 25, color, 3); line(data, 62, 25, 62, 35, color, 3)
  },
  fund(data, color) {
    circle(data, 40, 40, 25, color); line(data, 29, 27, 51, 27, color, 3)
    line(data, 40, 27, 40, 58, color, 3); line(data, 31, 36, 49, 36, color, 3)
    line(data, 32, 36, 40, 44, color, 3); line(data, 48, 36, 40, 44, color, 3)
  },
  ai(data, color) {
    rect(data, 16, 20, 49, 39, color); line(data, 28, 59, 23, 68, color, 3)
    circle(data, 31, 39, 2, color, 3); circle(data, 50, 39, 2, color, 3)
  }
}

function png(data) {
  const raw = Buffer.alloc((SIZE * 4 + 1) * SIZE)
  for (let y = 0; y < SIZE; y += 1) {
    const row = y * (SIZE * 4 + 1)
    raw[row] = 0
    Buffer.from(data.buffer, y * SIZE * 4, SIZE * 4).copy(raw, row + 1)
  }
  const header = Buffer.alloc(13)
  header.writeUInt32BE(SIZE, 0); header.writeUInt32BE(SIZE, 4)
  header[8] = 8; header[9] = 6
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk('IHDR', header), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))
  ])
}

const output = path.resolve(__dirname, '..', 'assets', 'tabbar')
fs.mkdirSync(output, { recursive: true })
for (const [name, draw] of Object.entries(icons)) {
  for (const [state, color] of Object.entries(COLORS)) {
    const data = canvas()
    draw(data, color)
    fs.writeFileSync(path.join(output, `${name}-${state}.png`), png(data))
  }
}
