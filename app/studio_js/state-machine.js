// modules/state-machine.js

window.StateMachine = (() => {
  const STATES = {
    IDLE:            'IDLE',
    SCAN:            'SCAN',
    OPEN:            'OPEN',
    DETAIL:          'DETAIL',
    UPLOAD_THUMB:    'UPLOAD_THUMB',
    MONETIZATION:    'MONETIZATION',
    CONTENT_RATINGS: 'CONTENT_RATINGS',
    VIDEO_ELEMENTS:  'VIDEO_ELEMENTS',
    END_SCREEN:      'END_SCREEN',
    CHECKS:          'CHECKS',
    VISIBILITY:      'VISIBILITY',
    PUBLISH:         'PUBLISH',
    SUCCESS:         'SUCCESS',
    NEXT:            'NEXT',
    ERROR:           'ERROR',
    CLOSE:           'CLOSE',
    DISCARD:         'DISCARD',
    BACK:            'BACK',
    DONE:            'DONE',
    STOPPED:         'STOPPED',
    SCHEDULE:        'SCHEDULE'
  };

  let currentState = STATES.IDLE;
  let onStateChange = null;

  async function transition(newState, statusText = '') {
    currentState = newState;
    await chrome.storage.local.set({ state: newState, statusText });
    if (onStateChange) onStateChange(newState, statusText);
  }

  function getState() { return currentState; }
  function onTransition(fn) { onStateChange = fn; }

  return { STATES, transition, getState, onTransition };
})();
