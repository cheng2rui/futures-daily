const VARIETY_NAMES = {
  'A': '大豆一号',
  'AD': '铸造铝合金',
  'AG': '白银',
  'AL': '铝',
  'AO': '氧化铝',
  'AP': '苹果',
  'AU': '黄金',
  'B': '大豆二号',
  'BB': '胶合板',
  'BC': '阴极铜',
  'BR': '丁二烯橡胶',
  'BU': '沥青',
  'BZ': '纯苯',
  'C': '黄玉米',
  'CF': '棉花',
  'CJ': '红枣',
  'CS': '玉米淀粉',
  'CU': '铜',
  'CY': '棉纱',
  'EB': '苯乙烯',
  'EC': '集运指数',
  'EG': '乙二醇',
  'FB': '细木工板',
  'FG': '玻璃',
  'FU': '燃料油',
  'HC': '热轧卷板',
  'I': '铁矿石',
  'IC': '中证500',
  'IF': '沪深300',
  'IH': '上证50',
  'IM': '中证1000',
  'J': '焦炭',
  'JD': '鸡蛋',
  'JM': '焦煤',
  'JR': '粳稻',
  'L': '聚乙烯',
  'LC': '碳酸锂',
  'LG': '原木',
  'LH': '生猪',
  'LR': '晚籼稻',
  'LU': '低硫燃料油',
  'M': '豆粕',
  'MA': '甲醇',
  'NI': '镍',
  'NR': '20号胶',
  'OI': '菜油',
  'OP': '胶版印刷纸',
  'P': '棕榈油',
  'PB': '铅',
  'PD': '钯',
  'PE': '聚乙烯',
  'PF': '短纤',
  'PG': '液化石油气',
  'PK': '花生',
  'PL': '丙烯',
  'PM': '普麦',
  'PP': '聚丙烯',
  'PR': '瓶片',
  'PS': '聚苯乙烯',
  'PT': '铂',
  'PX': '对二甲苯',
  'RB': '螺纹钢',
  'RI': '早籼稻',
  'RM': '菜粕',
  'RR': '粳米',
  'RS': '油菜籽',
  'RU': '天然橡胶',
  'SA': '纯碱',
  'SC': '原油',
  'SF': '硅铁',
  'SH': '烧碱',
  'SI': '工业硅',
  'SM': '锰硅',
  'SN': '锡',
  'SP': '纸浆',
  'SR': '白糖',
  'SS': '不锈钢',
  'T': '5年期国债',
  'TA': 'PTA',
  'TF': '10年期国债',
  'TL': '30年期国债',
  'TS': '2年期国债',
  'UR': '尿素',
  'V': '聚氯乙烯',
  'WH': '强麦',
  'WR': '线材',
  'Y': '豆油',
  'ZC': '动力煤',
  'ZN': '锌',
}

const EXCHANGE_NAMES = {
  SHFE: '上期所',
  DCE: '大商所',
  CZCE: '郑商所',
  CFFEX: '中金所',
  GFEX: '广期所',
  INE: '上期能源',
  ALL: '全部',
}

export function exchangeName(code) {
  const key = String(code || '').toUpperCase()
  return EXCHANGE_NAMES[key] || code || '-'
}

export function exchangeOptions(codes = []) {
  return codes.map(code => ({ code, name: exchangeName(code) }))
}

export function varietyName(symbol) {
  const key = String(symbol || '').toUpperCase()
  return VARIETY_NAMES[key] || symbol || '-'
}

export function fullContractCode(contract) {
  const text = String(contract || '').toUpperCase().trim()
  if (!text) return '-'
  return text.replace(/^([A-Z_]+)(\d{3})$/, (_, prefix, ym) => `${prefix}2${ym}`)
}

export function contractDisplay(contract, symbol = '', options = {}) {
  const code = fullContractCode(contract)
  if (!code || code === '-') return '-'
  const variety = varietyName(symbol)
  const text = variety && variety !== symbol ? `${variety} ${code}` : code
  return options.main ? `主力合约 ${text}` : text
}

export function contractName(contract, symbol = '') {
  return contractDisplay(contract, symbol)
}
