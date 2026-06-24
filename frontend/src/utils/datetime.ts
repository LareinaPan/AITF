const BEIJING_TIMEZONE = 'Asia/Shanghai'

const beijingDateTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  timeZone: BEIJING_TIMEZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
})

/** Parse API datetime strings; timezone-less values are treated as UTC. */
export function parseApiDateTime(value: string | Date): Date {
  if (value instanceof Date) {
    return value
  }

  const normalized = value.trim().replace(' ', 'T')
  const hasTimezone = /(?:[zZ]|[+-]\d{2}:\d{2})$/.test(normalized)
  return new Date(hasTimezone ? normalized : `${normalized}Z`)
}

/** Format an ISO datetime string (or Date) as Beijing time (UTC+8). */
export function formatBeijingTime(value: string | Date | null | undefined): string {
  if (value === null || value === undefined || value === '') {
    return '—'
  }

  const date = parseApiDateTime(value)
  if (Number.isNaN(date.getTime())) {
    return '—'
  }

  return beijingDateTimeFormatter.format(date)
}
