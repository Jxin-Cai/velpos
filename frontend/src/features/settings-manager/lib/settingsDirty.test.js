import assert from 'node:assert/strict'
import test from 'node:test'

import {
  isChannelFormDirty,
  isSettingsWorkingCopyDirty,
} from './settingsDirty.js'

const EMPTY_CHANNEL_FORM = {
  name: '',
  host: '',
  api_key: '',
  auth_env_name: 'ANTHROPIC_API_KEY',
  model_config: {},
}

test('test_keeps_add_form_clean_when_inputs_bind_empty_model_keys', () => {
  // Arrange
  const form = {
    ...EMPTY_CHANNEL_FORM,
    model_config: { ANTHROPIC_MODEL: '', ANTHROPIC_DEFAULT_SONNET_MODEL: undefined },
  }

  // Act
  const dirty = isChannelFormDirty(form, EMPTY_CHANNEL_FORM)

  // Assert
  assert.equal(dirty, false)
})

test('test_marks_add_form_dirty_when_name_is_filled', () => {
  // Arrange
  const form = { ...EMPTY_CHANNEL_FORM, name: '生产环境' }

  // Act
  const dirty = isChannelFormDirty(form, EMPTY_CHANNEL_FORM)

  // Assert
  assert.equal(dirty, true)
})

test('test_keeps_edit_form_clean_when_missing_model_keys_are_bound_as_empty_strings', () => {
  // Arrange
  const profile = {
    name: 'prod',
    host: 'https://api.anthropic.com',
    api_key: 'sk-test',
    auth_env_name: 'ANTHROPIC_API_KEY',
    model_config: { ANTHROPIC_DEFAULT_SONNET_MODEL: 'sonnet' },
  }
  const form = {
    ...profile,
    model_config: {
      ANTHROPIC_DEFAULT_SONNET_MODEL: 'sonnet',
      ANTHROPIC_MODEL: '',
    },
  }

  // Act
  const dirty = isChannelFormDirty(form, profile)

  // Assert
  assert.equal(dirty, false)
})

test('test_keeps_settings_clean_when_baseline_includes_display_default_writes', () => {
  // Arrange
  const loaded = { hasCompletedOnboarding: true, env: { CLAUDE_CODE_ENABLE_TELEMETRY: '1' } }
  const working = {
    ...loaded,
    permissions: { defaultMode: 'default' },
    attribution: { commit: '' },
  }
  const baseline = JSON.stringify(working)

  // Act
  const dirty = isSettingsWorkingCopyDirty(baseline, working)

  // Assert
  assert.equal(dirty, false)
})

test('test_marks_settings_dirty_when_user_changes_a_field_after_baseline', () => {
  // Arrange
  const baseline = JSON.stringify({ hasCompletedOnboarding: true, permissions: { defaultMode: 'default' } })
  const working = { hasCompletedOnboarding: true, permissions: { defaultMode: 'plan' } }

  // Act
  const dirty = isSettingsWorkingCopyDirty(baseline, working)

  // Assert
  assert.equal(dirty, true)
})

test('test_keeps_settings_clean_when_baseline_has_not_been_captured', () => {
  // Arrange
  const working = { permissions: { defaultMode: 'default' } }

  // Act
  const dirty = isSettingsWorkingCopyDirty('', working)

  // Assert
  assert.equal(dirty, false)
})
