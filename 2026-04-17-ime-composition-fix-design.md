# IME Input Method Composition Fix Design

**Date:** 2026-04-17
**Status:** Approved
**Component:** Message Input Feature

## Problem Statement

Users experiencing interference when using Input Method Editors (IME) for Chinese, Japanese, or other non-Latin languages. When confirming text selection via Enter key during IME composition, the message is unexpectedly sent instead of confirming the IME selection.

### Current Behavior
- User types "nihao" in Pinyin IME
- IME shows candidate selection box
- User presses Enter to confirm selection
- Message is sent instead of confirming IME selection

### Expected Behavior
- During IME composition, Enter key should confirm IME selection
- Only after IME composition ends should Enter key send message
- This should work for both Enter and Ctrl+Enter combinations

## Solution Design

### Technical Approach

Use standard Web Composition Events to track IME state and conditionally handle Enter key events.

**Key Insight:** Browser provides `compositionstart` and `compositionend` events to track IME lifecycle. During composition, all Enter key handling should be suppressed.

### Implementation Changes

**File:** `frontend/src/features/send-message/ui/MessageInput.vue`

#### 1. Add Composition State

```javascript
// In setup() function
const isComposing = ref(false)
```

#### 2. Add Composition Event Handlers

```javascript
function handleCompositionStart() {
  isComposing.value = true
}

function handleCompositionEnd() {
  isComposing.value = false
}
```

#### 3. Update handleKeydown Function

```javascript
function handleKeydown(e) {
  if (e.key === 'Enter') {
    // During IME composition, defer all Enter handling to browser default
    if (isComposing.value) {
      return
    }

    // Existing Enter handling logic (unchanged)
    const hasCtrl = e.ctrlKey
    const hasCmd = e.metaKey
    const hasModifier = hasCtrl || hasCmd

    if (shouldEnterSend() && !hasModifier) {
      e.preventDefault()
      handleSend()
    } else if (shouldCtrlEnterSend() && hasModifier) {
      e.preventDefault()
      handleSend()
    } else if (hasModifier) {
      e.preventDefault()
      // Manual newline insertion...
    }
  }
}
```

#### 4. Add Event Listeners to Template

```vue
<textarea
  ref="inputEl"
  v-model="input"
  @keydown="handleKeydown"
  @compositionstart="handleCompositionStart"
  @compositionend="handleCompositionEnd"
  @paste="handlePaste"
  ...
/>
```

### User Interaction Flow

#### Scenario 1: Pinyin Input with Enter-to-Send Mode
1. User types "nihao" → IME activates, `compositionstart` fires, `isComposing = true`
2. User presses Enter → `isComposing` check triggers early return, IME confirms "你好"
3. `compositionend` fires, `isComposing = false`
4. User presses Enter again → Normal message send

#### Scenario 2: Chinese Input with Ctrl+Enter-to-Send Mode
1. User types Chinese characters → `isComposing = true`
2. User presses Ctrl+Enter → Early return, IME handles normally
3. IME completes → `isComposing = false`
4. User presses Ctrl+Enter → Message sends

#### Scenario 3: English Input (No IME)
1. User types English text → `isComposing = false`
2. User presses Enter (or Ctrl+Enter) → Normal handling per user preferences

### Edge Cases Handled

1. **Quick composition**: Fast typists who rapidly compose and send
2. **IME cancellation**: User cancels IME (Escape key) → `compositionend` still fires
3. **Mixed input**: Alternating between IME and direct text input
4. **All Enter variants**: Enter, Ctrl+Enter, Cmd+Enter all suppressed during composition
5. **User preferences**: Works with both Enter-to-Send and Ctrl+Enter-to-Send modes

## Testing Plan

### Manual Test Cases

1. **Chinese Pinyin Input**
   - Type Pinyin, select candidate with Enter
   - Verify message does not send
   - Press Enter again to send

2. **Chinese Wubi Input**
   - Type Wubi code, press Enter to confirm
   - Verify proper IME handling

3. **Japanese IME**
   - Input Romaji, convert to Kanji
   - Verify Enter confirms selection, not send

4. **English Direct Input**
   - Type English text, press Enter
   - Verify normal send behavior

5. **Ctrl+Enter with IME**
   - Activate IME, press Ctrl+Enter
   - Verify IME handles normally, not send

6. **User Preference Modes**
   - Test both Enter-to-Send and Ctrl+Enter-to-Send modes
   - Verify IME works correctly in both

### Browser Compatibility

- Chrome/Edge: Full support
- Firefox: Full support
- Safari: Full support (composition events since Safari 10.1)
- Legacy browsers: Graceful degradation to original behavior

## Impact Assessment

### Changed Files
- `frontend/src/features/send-message/ui/MessageInput.vue`

### Risk Level
**Low** - Minimal, focused change with well-established web standards

### Breaking Changes
None - change is purely additive and defensive

### Performance Impact
Negligible - Two additional event handlers with simple boolean flag

## Rollout Plan

1. Implement changes in MessageInput.vue
2. Test manually with Chinese/Japanese IME
3. Verify existing functionality unchanged
4. Deploy to development environment for further testing

## Success Criteria

- IME composition completes without triggering message send
- Message send works correctly after IME composition ends
- Existing keyboard shortcuts (Enter/Ctrl+Enter) work as before
- No regression in English input or other features
