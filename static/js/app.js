/* KaamMitr — Shared JS Utilities */

// ── Storage ────────────────────────────────────────────────────────
const KM = {
  getPhone: () => localStorage.getItem('km_phone') || '',
  setPhone: (p) => localStorage.setItem('km_phone', p),
  getLang:  () => localStorage.getItem('km_lang') || 'hi',
  setLang:  (l) => localStorage.setItem('km_lang', l),

  // ── API with retry ───────────────────────────────────────────────
  async api(method, path, body = null, retries = 1) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    for (let i = 0; i <= retries; i++) {
      try {
        const res = await fetch(path, opts);
        if (res.status === 429) {
          await new Promise(r => setTimeout(r, 1500));
          continue;
        }
        return await res.json();
      } catch (e) {
        if (i === retries) return { success: false, message: 'Network error' };
        await new Promise(r => setTimeout(r, 800));
      }
    }
    return { success: false, message: 'Network error' };
  },

  // ── Toast ────────────────────────────────────────────────────────
  _toastTimer: null,
  toast(msg, type = 'default', duration = 3500) {
    const el = document.getElementById('km-toast');
    if (!el) return;
    const icons = { default: '✦', success: '✓', error: '✕', info: 'ℹ' };
    el.querySelector('.t-icon').textContent = icons[type] || '✦';
    el.querySelector('.t-msg').textContent  = msg;
    el.classList.add('show');
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => el.classList.remove('show'), duration);
  },

  // ── Format ───────────────────────────────────────────────────────
  esc(s) {
    return String(s || '')
      .replace(/&/g,'&amp;').replace(/</g,'&lt;')
      .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  },
  currency(n) { return '₹' + Number(n || 0).toLocaleString('en-IN'); },
  cap(s)      { return s ? s.charAt(0).toUpperCase() + s.slice(1) : ''; },

  // ── Scroll fade observer ─────────────────────────────────────────
  initFadeUp() {
    const obs = new IntersectionObserver(entries => {
      entries.forEach(e => {
        if (e.isIntersecting) { e.target.classList.add('visible'); obs.unobserve(e.target); }
      });
    }, { threshold: 0.1 });
    document.querySelectorAll('.fade-up').forEach(el => obs.observe(el));
  },

  // ── Active nav ───────────────────────────────────────────────────
  highlightNav() {
    const p = window.location.pathname;
    document.querySelectorAll('.navbar-links a').forEach(a => {
      const href = a.getAttribute('href');
      const active = (href === '/home' && p === '/home') ||
                     (href !== '/home' && href !== '/' && p.startsWith(href));
      a.classList.toggle('active', active);
    });
  },

  // ── Ripple ───────────────────────────────────────────────────────
  ripple(btn) {
    const r = document.createElement('span');
    r.style.cssText = 'position:absolute;border-radius:50%;pointer-events:none;width:8px;height:8px;background:rgba(255,255,255,.4);animation:ripple-anim .5s ease-out forwards;left:50%;top:50%;transform:translate(-50%,-50%);';
    btn.style.position = 'relative';
    btn.style.overflow = 'hidden';
    btn.appendChild(r);
    setTimeout(() => r.remove(), 500);
  }
};

const _rs = document.createElement('style');
_rs.textContent = '@keyframes ripple-anim{to{transform:translate(-50%,-50%) scale(12);opacity:0}}';
document.head.appendChild(_rs);


// ── TTS helper ────────────────────────────────────────────────────
const TTS = {
  speak(text, lang = 'hi') {
    if (!window.speechSynthesis) return;
    const clean = text
      .replace(/[\u{1F000}-\u{1FFFF}]/gu, '')
      .replace(/[\u2600-\u27BF]/g, '')
      .replace(/[*#_~`\[\]]/g, '')
      .replace(/\n/g, '. ')
      .replace(/\.{2,}/g, '.')
      .replace(/\s{2,}/g, ' ')
      .trim()
      .slice(0, 400);
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(clean);
    const langMap = { hi: 'hi-IN', en: 'en-IN', te: 'te-IN' };
    u.lang  = langMap[lang] || 'hi-IN';
    u.rate  = 0.88;
    u.pitch = 1.0;
    window.speechSynthesis.speak(u);
  },
  stop() { window.speechSynthesis?.cancel(); }
};


// ── Trust score ring ──────────────────────────────────────────────
function renderTrustRing(score, size = 72) {
  const r    = (size / 2) - 6;
  const circ = 2 * Math.PI * r;
  const fill = (score / 100) * circ;
  return `
    <div class="trust-ring" style="width:${size}px;height:${size}px">
      <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
        <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="var(--border)" stroke-width="5"/>
        <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="var(--clay)" stroke-width="5"
          stroke-linecap="round" stroke-dasharray="${fill} ${circ}"
          style="transition:stroke-dasharray .8s var(--ease-out)"/>
      </svg>
      <span class="trust-ring-val" style="font-size:${size/5}px">${Math.round(score)}</span>
    </div>`;
}


// ── Trust badge (Task 2) ──────────────────────────────────────────
function renderTrustBadge(data) {
  const { name, skill, avg_rating, jobs_completed, verified, trust_score } = data;
  const stars = '⭐'.repeat(Math.round(avg_rating || 0));
  const badge = verified ? '✅ Verified' : '🔄 Building Trust';
  return `
    <div style="display:flex;align-items:center;gap:12px;background:var(--sand);
                border-radius:14px;padding:14px 16px;border:1px solid var(--border)">
      ${renderTrustRing(trust_score || 50, 52)}
      <div>
        <div style="font-weight:700;font-size:.9rem">${KM.esc(name || 'Worker')}</div>
        <div style="font-size:.78rem;color:var(--muted)">${KM.cap(skill || 'General')}</div>
        <div style="font-size:.75rem;margin-top:3px">
          ${stars || '—'} ${avg_rating > 0 ? avg_rating : ''} &nbsp;|&nbsp;
          ${jobs_completed} jobs &nbsp;|&nbsp;
          <span style="color:${verified ? 'var(--forest)' : 'var(--muted)'}">${badge}</span>
        </div>
      </div>
    </div>`;
}


// ── Job card builder ──────────────────────────────────────────────
function buildJobCard(job, opts = {}) {
  const { compact = false, showApply = true } = opts;
  const isSkilled = job.job_type === 'skilled';
  const lang = KM.getLang() || 'hi';
  const applyTxt = { hi: 'Apply Karein', en: 'Apply Now', te: 'దరఖాస్తు చేయండి' };
  const applyLabel = applyTxt[lang] || applyTxt.en;
  return `
    <div class="job-card ${isSkilled ? 'skilled' : ''} fade-up">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:12px">
        <div>
          <div class="job-card-title">${KM.esc(job.title)}</div>
          ${job.description && !compact
            ? `<p style="font-size:.76rem;color:var(--muted);margin-top:5px;line-height:1.5">${KM.esc(job.description)}</p>`
            : ''}
        </div>
        <span class="badge ${isSkilled ? 'badge-skilled' : 'badge-instant'}" style="white-space:nowrap">
          ${isSkilled ? '🧠 Skilled' : '⚡ Instant'}
        </span>
      </div>
      <div class="job-card-meta">
        <span>📍 ${KM.esc(job.location || 'Nearby')}</span>
        <span>⏱ ${KM.esc(job.duration || '—')}</span>
        ${job.skill_required ? `<span>🛠 ${KM.cap(job.skill_required)}</span>` : ''}
      </div>
      <div style="display:flex;align-items:center;justify-content:space-between;margin-top:14px">
        <div class="job-salary">${KM.currency(job.salary)}<span>/${job.salary_unit || 'day'}</span></div>
        ${showApply ? `
        <a class="btn btn-success btn-sm" href="/job-apply/${job.id}">
          ${applyLabel}
        </a>` : ''}
      </div>
    </div>`;
}


// ── Apply to job — full confirmation card ─────────────────────────
async function applyJob(jobId, jobData) {
  const phone = KM.getPhone();
  const lang  = KM.getLang() || 'hi';
  const _applyL = {
    hi: { login: 'Pehle login karein!', submitted: 'Application Submit Ho Gayi!', contact: 'Employer jald hi contact karega. Profile mein track karein.', track: 'Track Karein', retry: 'Apply Nahi Hua' },
    en: { login: 'Please login first!', submitted: 'Application Submitted!', contact: 'Employer will contact you soon. Track in Profile.', track: 'Track Application', retry: 'Could not apply' },
    te: { login: 'ముందు లాగిన్ చేయండి!', submitted: 'దరఖాస్తు సమర్పించబడింది!', contact: 'యజమాని త్వరలో సంప్రదిస్తారు. ప్రొఫైల్‌లో ట్రాక్ చేయండి.', track: 'ట్రాక్ చేయండి', retry: 'దరఖాస్తు కాలేదు' }
  };
  const AL = _applyL[lang] || _applyL.en;

  if (!phone) {
    KM.toast(AL.login, 'error');
    setTimeout(() => window.location.href = '/login', 1200);
    return;
  }

  const btn = document.getElementById(`jbtn-${jobId}`);
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="km-spin"></span>'; }

  const res = await KM.api('POST', `/api/jobs/${jobId}/apply`, { phone }, 1);

  if (res.success) {
    const d = res.data || {};
    const msgs = document.getElementById('msgs');
    if (msgs) {
      const card = document.createElement('div');
      card.className = 'msg-row bot';
      card.innerHTML = `
        <div class="bot-avatar">🤖</div>
        <div style="flex:1;max-width:420px">
          <div style="background:var(--forest-pale);border:2px solid var(--forest);
                      border-radius:18px;padding:18px 20px;
                      animation:bubble-in .3s var(--ease-back) both">
            <div style="font-weight:900;font-size:1rem;color:var(--forest);margin-bottom:12px">
              ✅ ${AL.submitted}
            </div>
            <div style="display:flex;flex-direction:column;gap:8px;font-size:.82rem">
              <div>📋 <strong>${KM.esc(d.job_title || '')}</strong></div>
              <div>📍 ${KM.esc(d.job_location || '')}</div>
              <div>💰 ${KM.currency(d.job_salary || 0)} / ${d.job_salary_unit || 'day'}</div>
              <div>⏱ ${KM.esc(d.job_duration || '')}</div>
              <div style="margin-top:6px;padding:8px 12px;background:var(--white);
                          border-radius:10px;font-family:monospace;font-size:.85rem;
                          color:var(--clay);font-weight:700;letter-spacing:.5px">
                🆔 ${d.application_id || ''}
              </div>
            </div>
            <div style="margin-top:12px;font-size:.75rem;color:var(--muted)">${AL.contact}</div>
            <a href="/profile?phone=${phone}"
               style="display:inline-flex;align-items:center;gap:6px;margin-top:10px;
                      padding:8px 16px;background:var(--forest);color:#fff;
                      border-radius:10px;font-size:.78rem;font-weight:700;text-decoration:none">
              📊 ${AL.track}
            </a>
          </div>
        </div>`;
      msgs.appendChild(card);
      msgs.scrollTop = msgs.scrollHeight + 999;
    } else {
      KM.toast(`✅ ${d.application_id || 'Applied!'} — ${d.job_title || ''}`, 'success', 5000);
    }

    if (btn) { btn.innerHTML = '✓'; btn.style.background = 'var(--forest)'; }
    if (window.speechSynthesis) {
      TTS.speak(`${AL.submitted} ${d.application_id || ''}`, lang);
    }

  } else {
    KM.toast(res.message || AL.retry, 'error');
    if (btn) { btn.disabled = false; btn.innerHTML = _applyL[lang]?.track || 'Apply'; }
  }
}


// ── Spinner ───────────────────────────────────────────────────────
const _ss = document.createElement('style');
_ss.textContent = `.km-spin{display:inline-block;width:14px;height:14px;border:2px solid rgba(255,255,255,.4);border-top-color:#fff;border-radius:50%;animation:km-sp .6s linear infinite}@keyframes km-sp{to{transform:rotate(360deg)}}`;
document.head.appendChild(_ss);


// ── Init ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  KM.highlightNav();
  KM.initFadeUp();
});
