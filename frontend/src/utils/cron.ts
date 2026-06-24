const CRON_FIELD_COUNT = 5

export function normalizeCronExpression(value: string): string {
  return value.trim()
}

export function validateCronExpression(
  value: string,
  options: { required?: boolean } = {},
): string | null {
  const trimmed = normalizeCronExpression(value)

  if (!trimmed) {
    return options.required ? '启用定时任务时必须填写 Cron 表达式' : null
  }

  const fields = trimmed.split(/\s+/)
  if (fields.length !== CRON_FIELD_COUNT) {
    return `Cron 表达式须为 ${CRON_FIELD_COUNT} 段格式：分 时 日 月 周（北京时间，如 50 10 * * 1-5）`
  }

  return null
}

export function createCronFormRule(options: { requiredWhen?: () => boolean } = {}) {
  return {
    validator: (_rule: unknown, value: string, callback: (error?: Error) => void) => {
      const required = options.requiredWhen?.() ?? false
      const message = validateCronExpression(value ?? '', { required })
      if (message) {
        callback(new Error(message))
        return
      }
      callback()
    },
    trigger: 'blur' as const,
  }
}
