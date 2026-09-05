// Universal Cross-Controller Client Engine for CryptoPad
(function() {
  const STICK_OFFSET = 22;
  const STICK_CURVING = 1;
  const ANALOGUE_STICK_THRESHOLD = 0.25;
  const ROTATE_BOUNDARY = 120;

  function lineDistance(point1, point2) {
    return Math.sqrt((point1 * point1) + (point2 * point2));
  }

  function updateAxis(value, valueV, gamepadId, stickId) {
    const gamepadEl = document.querySelector('#gamepad-' + gamepadId);
    if (!gamepadEl) return;

    const stickEl = gamepadEl.querySelector('[data-name="' + stickId + '"]');
    if (stickEl) {
      let offsetValH = 0, offsetValV = 0;
      if (lineDistance(value, valueV) >= ANALOGUE_STICK_THRESHOLD) {
        offsetValH = value * STICK_OFFSET;
        offsetValV = valueV * STICK_OFFSET;
      }
      stickEl.style.marginLeft = offsetValH + 'px';
      stickEl.style.marginTop = offsetValV + 'px';
      if (STICK_CURVING) {
        stickEl.style.transform = 'rotateX(' + (offsetValV * -1) + 'deg) rotateY(' + offsetValH + 'deg)';
      }
    }

    const stickRotEL = gamepadEl.querySelector('[data-name="' + stickId + '-wheel"]');
    if (stickRotEL) {
      const rotValH = lineDistance(value, valueV) >= ANALOGUE_STICK_THRESHOLD ? value : 0;
      stickRotEL.style.transform = 'rotate(' + (rotValH * ROTATE_BOUNDARY) + 'deg)';
    }
  }

  const socket = io();
  socket.on('reload_page', function() {
    console.log('Template changed, reloading page...');
    window.location.reload(true);
  });

  let lastDataTimestamp = Date.now();
  const controller = document.getElementById('gamepad-0');

  setInterval(() => {
    if (Date.now() - lastDataTimestamp > 5000) {
      if (controller) controller.classList.add('invisible');
    }
  }, 1000);

  function setPressed(id, isPressed) {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('pressed', !!isPressed);
  }

  socket.on('controller_data', data => {
    lastDataTimestamp = Date.now();
    if (controller) controller.classList.remove('invisible');

    // Cross-Controller Normalized State
    if (data.standard) {
      const s = data.standard;

      // Face Buttons (A / Cross, B / Circle, X / Square, Y / Triangle)
      setPressed('a', s.a);
      setPressed('b', s.b);
      setPressed('x', s.x);
      setPressed('y', s.y);

      // Shoulders / Bumpers (LB / L1, RB / R1)
      setPressed('lb', s.lb);
      setPressed('rb', s.rb);

      // Navigation (Select / Back / Share, Start / Options / Menu)
      setPressed('select', s.select);
      setPressed('start', s.start);

      // Meta (PS / Guide) & Touchpad
      setPressed('meta', s.meta);
      setPressed('touchpad', s.touchpad);

      // Triggers (Analog Opacity 0.0 - 1.0)
      const ltEl = document.getElementById('lt-fill');
      const rtEl = document.getElementById('rt-fill');
      if (ltEl) ltEl.style.opacity = Math.max(0, Math.min(1, s.lt));
      if (rtEl) rtEl.style.opacity = Math.max(0, Math.min(1, s.rt));

      // D-Pad
      setPressed('dpad-up', s.dpad_up);
      setPressed('dpad-down', s.dpad_down);
      setPressed('dpad-left', s.dpad_left);
      setPressed('dpad-right', s.dpad_right);

      // Analog Thumbsticks
      updateAxis(s.left_stick_x, s.left_stick_y, 0, 'stick-1');
      updateAxis(s.right_stick_x, s.right_stick_y, 0, 'stick-2');

      // Stick Clicks (L3, R3)
      setPressed('left-stick', s.ls);
      setPressed('right-stick', s.rs);
      return;
    }

    // Legacy Raw Fallback
    const buttons = data.buttons || [];
    const axes = data.axes || [];
    const hats = data.hats || [[0, 0]];
    ['a', 'b', 'x', 'y'].forEach((id, i) => setPressed(id, buttons[i] === 1));
    setPressed('lb', buttons[4] === 1 || buttons[9] === 1);
    setPressed('rb', buttons[5] === 1 || buttons[10] === 1);
    setPressed('select', buttons[6] === 1 || buttons[4] === 1);
    setPressed('start', buttons[7] === 1 || buttons[6] === 1);
  });
})();
