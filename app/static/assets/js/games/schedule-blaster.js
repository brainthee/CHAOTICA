/**
 * Schedule Blaster - Space Invaders with your schedule slots as aliens
 * Extracts FullCalendar events and converts them to descending invaders
 */
window.ScheduleBlaster = (function() {
    'use strict';

    var running = false;
    var gameCanvas = null;
    var gameCtx = null;
    var animId = null;

    // Game state
    var ship = null;
    var bullets = [];
    var invaders = [];
    var keys = {};
    var lastTime = 0;
    var gameOver = false;
    var victory = false;

    // Constants
    var SHIP_WIDTH = 50;
    var SHIP_HEIGHT = 30;
    var SHIP_SPEED = 400;
    var BULLET_SPEED = 600;
    var MAX_BULLETS = 10;
    var FIRE_COOLDOWN = 0.06; // seconds
    var INVADER_SPEED = 25; // px/sec base, increases
    var INVADER_ROWS = 0;
    var INVADER_COLS = 8;
    var INVADER_H = 32;
    var INVADER_PAD_X = 12;
    var INVADER_PAD_Y = 10;

    var fireCooldownTimer = 0;
    var speedMultiplier = 1;
    var flashTimers = {};

    function start() {
        if (running) return;

        // Get events from FullCalendar
        if (typeof calendar === 'undefined' || !calendar) {
            Swal.fire({
                title: 'NO TARGET DATA',
                text: 'Calendar system not initialized.',
                icon: 'warning',
                background: '#1a1a2e',
                color: '#FF9900'
            });
            return;
        }

        var events = calendar.getEvents();
        if (!events.length) {
            Swal.fire({
                title: 'NO HOSTILES DETECTED',
                text: 'No schedule events found to blast.',
                icon: 'info',
                background: '#1a1a2e',
                color: '#FF9900'
            });
            return;
        }

        running = true;
        gameOver = false;
        victory = false;
        bullets = [];
        invaders = [];
        keys = {};
        fireCooldownTimer = 0;
        speedMultiplier = 1;
        flashTimers = {};

        // Hide calendar
        var calEl = document.getElementById('calendar');
        if (calEl) calEl.style.display = 'none';
        // Hide offcanvas toggle
        var settingToggle = document.querySelector('.setting-toggle');
        if (settingToggle) settingToggle.style.display = 'none';

        // Create game canvas (this one IS interactive)
        gameCanvas = document.createElement('canvas');
        gameCanvas.id = 'blaster-canvas';
        gameCanvas.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:99997;background:#0a0a1a;';
        gameCanvas.width = window.innerWidth;
        gameCanvas.height = window.innerHeight;
        document.body.appendChild(gameCanvas);
        gameCtx = gameCanvas.getContext('2d');

        // Init ChaosEngine canvas for particles on top
        ChaosEngine.canvas.init();
        ChaosEngine.score.start('blaster');

        // Build invaders from events
        buildInvaders(events);

        // Init ship
        ship = {
            x: gameCanvas.width / 2 - SHIP_WIDTH / 2,
            y: gameCanvas.height - SHIP_HEIGHT - 20,
            width: SHIP_WIDTH,
            height: SHIP_HEIGHT
        };

        // Input handlers
        document.addEventListener('keydown', onKeyDown);
        document.addEventListener('keyup', onKeyUp);

        window.addEventListener('resize', onResize);

        lastTime = 0;
        animId = requestAnimationFrame(gameLoop);
    }

    function stop() {
        running = false;
        if (animId) cancelAnimationFrame(animId);
        document.removeEventListener('keydown', onKeyDown);
        document.removeEventListener('keyup', onKeyUp);
        window.removeEventListener('resize', onResize);

        if (gameCanvas && gameCanvas.parentNode) {
            gameCanvas.parentNode.removeChild(gameCanvas);
        }
        gameCanvas = null;
        gameCtx = null;

        ChaosEngine.score.saveHighScore();
        ChaosEngine.score.hide();

        // Restore calendar
        var calEl = document.getElementById('calendar');
        if (calEl) {
            calEl.style.display = '';
            if (typeof calendar !== 'undefined' && calendar) calendar.render();
        }
        var settingToggle = document.querySelector('.setting-toggle');
        if (settingToggle) settingToggle.style.display = '';
    }

    function buildInvaders(events) {
        // Convert FullCalendar events to invader data
        var invaderData = [];
        for (var i = 0; i < events.length; i++) {
            var ev = events[i];
            var start = ev.start;
            var end = ev.end || new Date(start.getTime() + 3600000);
            var durationHours = (end - start) / 3600000;
            var title = (ev.title || 'Slot').substring(0, 14);
            var color = ev.backgroundColor || '#6688CC';
            var textColor = ev.textColor || '#FFFFFF';

            invaderData.push({
                title: title,
                color: color,
                textColor: textColor,
                hp: Math.max(1, Math.min(5, Math.ceil(durationHours / 16))),
                maxHp: Math.max(1, Math.min(5, Math.ceil(durationHours / 16))),
                width: Math.max(60, Math.min(100, 60 + durationHours * 2)),
                height: INVADER_H,
                points: Math.ceil(durationHours * 100)
            });
        }

        // Limit to reasonable number
        if (invaderData.length > 48) {
            invaderData = invaderData.slice(0, 48);
        }

        // Arrange in grid
        var cols = Math.min(INVADER_COLS, invaderData.length);
        var rows = Math.ceil(invaderData.length / cols);
        var maxW = 100;
        var totalGridW = cols * (maxW + INVADER_PAD_X);
        var startX = (gameCanvas.width - totalGridW) / 2 + INVADER_PAD_X / 2;
        var startY = 60;

        for (var j = 0; j < invaderData.length; j++) {
            var col = j % cols;
            var row = Math.floor(j / cols);
            var inv = invaderData[j];
            inv.x = startX + col * (maxW + INVADER_PAD_X) + (maxW - inv.width) / 2;
            inv.y = startY + row * (INVADER_H + INVADER_PAD_Y);
            inv.alive = true;
            inv.flashTimer = 0;
            invaders.push(inv);
        }
    }

    function onKeyDown(e) {
        keys[e.key] = true;
        if (e.key === 'Escape') {
            e.preventDefault();
            stop();
            return;
        }
        if (e.key === ' ' || e.key === 'ArrowUp' || e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
            e.preventDefault();
        }
    }
    function onKeyUp(e) { keys[e.key] = false; }

    function onResize() {
        if (gameCanvas) {
            gameCanvas.width = window.innerWidth;
            gameCanvas.height = window.innerHeight;
            if (ship) {
                ship.y = gameCanvas.height - SHIP_HEIGHT - 20;
            }
        }
    }

    function gameLoop(timestamp) {
        if (!running) return;
        var dt = lastTime ? (timestamp - lastTime) / 1000 : 0.016;
        lastTime = timestamp;
        if (dt > 0.1) dt = 0.016;

        if (!gameOver && !victory) {
            update(dt);
        }
        draw();
        animId = requestAnimationFrame(gameLoop);
    }

    function update(dt) {
        // Ship movement
        if ((keys['ArrowLeft'] || keys['a'] || keys['A']) && ship.x > 0) {
            ship.x -= SHIP_SPEED * dt;
        }
        if ((keys['ArrowRight'] || keys['d'] || keys['D']) && ship.x + ship.width < gameCanvas.width) {
            ship.x += SHIP_SPEED * dt;
        }
        ship.x = Math.max(0, Math.min(gameCanvas.width - ship.width, ship.x));

        // Firing
        fireCooldownTimer -= dt;
        if ((keys[' '] || keys['ArrowUp']) && fireCooldownTimer <= 0 && bullets.length < MAX_BULLETS) {
            fireCooldownTimer = FIRE_COOLDOWN;
            bullets.push({
                x: ship.x + ship.width / 2 - 2,
                y: ship.y - 8,
                width: 4,
                height: 12
            });
            ChaosEngine.sound.laser();
        }

        // Update bullets
        for (var i = bullets.length - 1; i >= 0; i--) {
            bullets[i].y -= BULLET_SPEED * dt;
            if (bullets[i].y < -20) {
                bullets.splice(i, 1);
            }
        }

        // Invader descent
        var aliveCount = 0;
        for (var j = 0; j < invaders.length; j++) {
            var inv = invaders[j];
            if (!inv.alive) continue;
            aliveCount++;
            inv.y += INVADER_SPEED * speedMultiplier * dt;
            if (inv.flashTimer > 0) inv.flashTimer -= dt;

            // Game over: invader reaches ship level
            if (inv.y + inv.height >= ship.y) {
                gameOver = true;
                onGameOver();
                return;
            }
        }

        if (aliveCount === 0) {
            victory = true;
            onVictory();
            return;
        }

        // Speed up as invaders are destroyed
        var totalInvaders = invaders.length;
        var destroyedRatio = (totalInvaders - aliveCount) / totalInvaders;
        speedMultiplier = 1 + destroyedRatio * 2;

        // Bullet-invader collision
        for (var bi = bullets.length - 1; bi >= 0; bi--) {
            var b = bullets[bi];
            for (var ii = 0; ii < invaders.length; ii++) {
                var target = invaders[ii];
                if (!target.alive) continue;
                if (rectsOverlap(b, target)) {
                    bullets.splice(bi, 1);
                    hitInvader(target);
                    break;
                }
            }
        }
    }

    function rectsOverlap(a, b) {
        return a.x < b.x + b.width && a.x + a.width > b.x &&
               a.y < b.y + b.height && a.y + a.height > b.y;
    }

    function hitInvader(inv) {
        inv.hp--;
        inv.flashTimer = 0.1;

        // Small hit particles
        var cx = inv.x + inv.width / 2;
        var cy = inv.y + inv.height / 2;
        ChaosEngine.particles.emit(cx, cy, {
            count: 5,
            colors: [inv.color, '#FFAA00'],
            speed: 80,
            lifetime: 0.3,
            size: 3
        });
        ChaosEngine.sound.hit();

        if (inv.hp <= 0) {
            inv.alive = false;

            // Big explosion
            ChaosEngine.particles.emit(cx, cy, {
                count: 25 + inv.maxHp * 5,
                colors: [inv.color, '#FF4444', '#FFAA00', '#FFD700'],
                speed: 200,
                lifetime: 0.7,
                size: 5
            });
            ChaosEngine.sound.explosion();
            ChaosEngine.score.add(inv.points, cx - 15, cy - 15);
            ChaosEngine.shake.trigger(3 + inv.maxHp, 150);
        }
    }

    function draw() {
        if (!gameCtx) return;
        var ctx = gameCtx;
        ctx.clearRect(0, 0, gameCanvas.width, gameCanvas.height);

        // Starfield background (simple)
        ctx.fillStyle = '#0a0a1a';
        ctx.fillRect(0, 0, gameCanvas.width, gameCanvas.height);

        // Draw invaders
        for (var i = 0; i < invaders.length; i++) {
            var inv = invaders[i];
            if (!inv.alive) continue;
            drawInvader(ctx, inv);
        }

        // Draw bullets
        ctx.fillStyle = '#00FF88';
        ctx.shadowColor = '#00FF88';
        ctx.shadowBlur = 6;
        for (var j = 0; j < bullets.length; j++) {
            var b = bullets[j];
            ctx.fillRect(b.x, b.y, b.width, b.height);
        }
        ctx.shadowBlur = 0;

        // Draw ship
        drawShip(ctx);

        // Game over / victory overlay
        if (gameOver) {
            drawOverlayText(ctx, 'HULL BREACH - GAME OVER', '#FF4444');
            drawSubText(ctx, 'Press ESCAPE to return to scheduling');
        }
        if (victory) {
            drawOverlayText(ctx, 'ALL HOSTILES ELIMINATED', '#00FF88');
            drawSubText(ctx, 'Press ESCAPE to return to scheduling');
        }

        // Controls hint
        if (!gameOver && !victory) {
            ctx.save();
            ctx.font = '12px monospace';
            ctx.fillStyle = 'rgba(153, 153, 255, 0.5)';
            ctx.textAlign = 'center';
            ctx.fillText('ARROWS/WASD: MOVE  |  SPACE: FIRE  |  ESC: EXIT', gameCanvas.width / 2, gameCanvas.height - 5);
            ctx.restore();
        }
    }

    function drawInvader(ctx, inv) {
        ctx.save();

        ctx.fillStyle = inv.color;

        // Rounded rect body
        roundRect(ctx, inv.x, inv.y, inv.width, inv.height, 4);
        ctx.fill();

        // Title text
        ctx.font = 'bold 10px monospace';
        ctx.fillStyle = inv.textColor || '#FFFFFF';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(inv.title, inv.x + inv.width / 2, inv.y + inv.height / 2);

        // HP bar (if multi-hp)
        if (inv.maxHp > 1) {
            var hpW = inv.width - 4;
            var hpH = 3;
            var hpX = inv.x + 2;
            var hpY = inv.y - hpH - 2;
            var hpRatio = inv.hp / inv.maxHp;

            ctx.fillStyle = '#333';
            ctx.fillRect(hpX, hpY, hpW, hpH);

            ctx.fillStyle = hpRatio > 0.5 ? '#00FF88' : (hpRatio > 0.25 ? '#FFAA00' : '#FF4444');
            ctx.fillRect(hpX, hpY, hpW * hpRatio, hpH);
        }

        ctx.restore();
    }

    function drawShip(ctx) {
        ctx.save();
        ctx.fillStyle = '#00CCFF';
        ctx.shadowColor = '#00CCFF';
        ctx.shadowBlur = 8;

        var cx = ship.x + ship.width / 2;
        var cy = ship.y;

        ctx.beginPath();
        ctx.moveTo(cx, cy - 5);                          // nose
        ctx.lineTo(cx + ship.width / 2, cy + ship.height); // right wing
        ctx.lineTo(cx + 4, cy + ship.height - 8);         // right inner
        ctx.lineTo(cx, cy + ship.height);                  // tail center
        ctx.lineTo(cx - 4, cy + ship.height - 8);         // left inner
        ctx.lineTo(cx - ship.width / 2, cy + ship.height); // left wing
        ctx.closePath();
        ctx.fill();

        // Engine glow
        ctx.fillStyle = '#FF6600';
        ctx.shadowColor = '#FF6600';
        ctx.beginPath();
        ctx.ellipse(cx, cy + ship.height + 2, 4, 6 + Math.random() * 3, 0, 0, Math.PI * 2);
        ctx.fill();

        ctx.restore();
    }

    function drawOverlayText(ctx, text, color) {
        ctx.save();
        ctx.font = 'bold 36px monospace';
        ctx.textAlign = 'center';
        ctx.fillStyle = color;
        ctx.shadowColor = color;
        ctx.shadowBlur = 15;
        ctx.fillText(text, gameCanvas.width / 2, gameCanvas.height / 2 - 20);
        ctx.restore();
    }

    function drawSubText(ctx, text) {
        ctx.save();
        ctx.font = '16px monospace';
        ctx.textAlign = 'center';
        ctx.fillStyle = '#9999FF';
        ctx.fillText(text, gameCanvas.width / 2, gameCanvas.height / 2 + 20);
        ctx.restore();
    }

    function roundRect(ctx, x, y, w, h, r) {
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.lineTo(x + w - r, y);
        ctx.quadraticCurveTo(x + w, y, x + w, y + r);
        ctx.lineTo(x + w, y + h - r);
        ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
        ctx.lineTo(x + r, y + h);
        ctx.quadraticCurveTo(x, y + h, x, y + h - r);
        ctx.lineTo(x, y + r);
        ctx.quadraticCurveTo(x, y, x + r, y);
        ctx.closePath();
    }

    function onGameOver() {
        ChaosEngine.sound.explosion(0.5);
        ChaosEngine.shake.trigger(20, 500);
        ChaosEngine.particles.emit(ship.x + ship.width / 2, ship.y + ship.height / 2, {
            count: 50,
            colors: ['#00CCFF', '#FF4444', '#FFAA00'],
            speed: 300,
            lifetime: 1.2,
            size: 6
        });
        ChaosEngine.score.saveHighScore();
    }

    function onVictory() {
        ChaosEngine.sound.powerUp();
        ChaosEngine.score.saveHighScore();

        // Celebration particles
        for (var i = 0; i < 5; i++) {
            setTimeout(function() {
                ChaosEngine.particles.emit(
                    Math.random() * gameCanvas.width,
                    Math.random() * gameCanvas.height * 0.5,
                    {
                        count: 20,
                        colors: ['#FFD700', '#00FF88', '#00CCFF', '#FF9900'],
                        speed: 150,
                        lifetime: 1.0,
                        size: 4
                    }
                );
            }, i * 300);
        }
    }

    return {
        start: start,
        stop: stop,
        isRunning: function() { return running; }
    };
})();
