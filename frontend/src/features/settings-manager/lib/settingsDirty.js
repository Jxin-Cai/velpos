export function compactModelConfig(config) {
  return Object.fromEntries(
    Object.entries(config || {}).filter(([, value]) => value != null && String(value) !== ''),
  )
}

export function channelFormSnapshot(form) {
  return JSON.stringify({
    name: form?.name || '',
    host: form?.host || '',
    api_key: form?.api_key || '',
    auth_env_name: form?.auth_env_name || 'ANTHROPIC_API_KEY',
    model_config: compactModelConfig(form?.model_config),
  })
}

export function isChannelFormDirty(form, initial) {
  return channelFormSnapshot(form) !== channelFormSnapshot(initial)
}

export function isSettingsWorkingCopyDirty(baseline, current) {
  return Boolean(baseline) && current != null && JSON.stringify(current) !== baseline
}
