import React, { useState, useEffect, useRef } from 'react';
import './index.css';

const SUPPORTED_DOMAINS = [
  'tiktok.com',
  'douyin.com',
  'iesdouyin.com',
  'facebook.com',
  'fb.watch',
  'instagram.com',
  'reddit.com',
  'redd.it',
  'v.redd.it',
  'redditmedia.com'
];

const getApiBaseUrl = () => {
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL;
  if (import.meta.env.PROD) return '';
  const hostname = window.location.hostname || '127.0.0.1';
  return `http://${hostname}:8000`;
};
const API_BASE_URL = getApiBaseUrl();

function App() {
  const [url, setUrl] = useState('');
  const [downloadType, setDownloadType] = useState('video');
  const [flip, setFlip] = useState(true);
  const [brighten, setBrighten] = useState(true);
  const [watermarkEnabled, setWatermarkEnabled] = useState(false);
  const [watermarkText, setWatermarkText] = useState('@SoSoCute Girl TH');
  const [watermarkPosition, setWatermarkPosition] = useState('bottom_right');
  const [watermarkOpacity, setWatermarkOpacity] = useState(0.25);
  const [antiDetection, setAntiDetection] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeJob, setActiveJob] = useState(null);
  const pollingIntervalRef = useRef(null);

  const validateUrl = (targetUrl) => {
    if (!targetUrl || !targetUrl.trim()) {
      return { valid: false, error: 'Please enter a valid video link, channel page URL, or copied page text.' };
    }
    
    const text = targetUrl.trim().toLowerCase();
    const hasSupportedKeyword = SUPPORTED_DOMAINS.some(domain => text.includes(domain)) || text.startsWith('r/');
    if (hasSupportedKeyword) {
      return { valid: true };
    }
    
    return { 
      valid: false, 
      error: 'Unsupported content. Please paste a valid link from TikTok, Douyin, Facebook, Instagram, or Reddit (Post / Subreddit).' 
    };
  };

  const clearPolling = () => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
  };

  // 1. Restore active/recent job on page refresh
  useEffect(() => {
    const restoreJob = async () => {
      const savedId = localStorage.getItem('last_job_id');
      if (savedId) {
        try {
          const res = await fetch(`${API_BASE_URL}/jobs/${savedId}`);
          if (res.ok) {
            const data = await res.json();
            setActiveJob(data);
            if (!['completed', 'error'].includes(data.status)) {
              setLoading(true);
            }
            return;
          }
        } catch (e) {
          console.warn("Failed to restore saved job from localStorage:", e);
        }
      }

      // Fallback: check if the server has an active/recent job
      try {
        const res = await fetch(`${API_BASE_URL}/jobs/latest`);
        if (res.ok) {
          const data = await res.json();
          if (data.has_job && data.job) {
            setActiveJob(data.job);
            if (!['completed', 'error'].includes(data.job.status)) {
              setLoading(true);
            }
          }
        }
      } catch (e) {
        // Backend not ready yet
      }
    };
    restoreJob();
  }, []);

  // 2. Poll job status with network safety & failure limits
  useEffect(() => {
    if (activeJob && !['completed', 'error'].includes(activeJob.status)) {
      let failureCount = 0;
      pollingIntervalRef.current = setInterval(async () => {
        try {
          const res = await fetch(`${API_BASE_URL}/jobs/${activeJob.id}`);
          if (res.status === 404) {
            clearPolling();
            setLoading(false);
            setError("งานนี้สิ้นสุดหรือระบบรีสตาร์ทแล้ว สามารถเริ่มดาวน์โหลดใหม่ได้ครับ");
            return;
          }
          if (res.ok) {
            failureCount = 0;
            const jobData = await res.json();
            setActiveJob(jobData);
            if (['completed', 'error'].includes(jobData.status)) {
              clearPolling();
              setLoading(false);
              if (jobData.status === 'error') {
                setError(jobData.error || 'Job encountered an error.');
              }
            }
          } else {
            failureCount++;
            if (failureCount >= 6) {
              clearPolling();
              setLoading(false);
              setError("การเชื่อมต่อขาดหายชั่วคราว กรุณากดรีเฟรชหน้าเว็บ");
            }
          }
        } catch (err) {
          failureCount++;
          if (failureCount >= 6) {
            clearPolling();
            setLoading(false);
            setError("ไม่สามารถติดต่อเซิร์ฟเวอร์ได้ กรุณาตรวจสอบสถานะ backend");
          }
        }
      }, 1500);
    } else {
      clearPolling();
    }

    return () => clearPolling();
  }, [activeJob?.id, activeJob?.status]);

  const handleResetJob = () => {
    clearPolling();
    setActiveJob(null);
    setError(null);
    setLoading(false);
    localStorage.removeItem('last_job_id');
  };

  const handleDownload = async (e) => {
    e.preventDefault();
    setError(null);
    setActiveJob(null);
    clearPolling();

    const check = validateUrl(url);
    if (!check.valid) {
      setError(check.error);
      return;
    }

    setLoading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/download_job`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          url: url.trim(),
          download_type: downloadType,
          flip: downloadType === 'video' && flip,
          brighten: downloadType === 'video' && brighten,
          watermark_text: (downloadType === 'video' && watermarkEnabled) ? watermarkText.trim() : '',
          watermark_position: watermarkPosition,
          watermark_opacity: watermarkOpacity,
          anti_detection: downloadType === 'video' && antiDetection
        }),
      });

      let data;
      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        data = await response.json();
      } else {
        throw new Error(`Server returned status ${response.status}: Unexpected non-JSON response.`);
      }

      if (!response.ok || !data.success) {
        throw new Error(data.error || 'Download request failed on the server.');
      }

      localStorage.setItem('last_job_id', data.job_id);

      setActiveJob({
        id: data.job_id,
        status: data.status,
        progress_message: "Initializing background extraction...",
        page_name: "Processing...",
        total_videos: 0,
        completed_videos: 0,
        items: []
      });
      setUrl('');
    } catch (err) {
      setError(err.message || 'Network error occurred while connecting to the download server.');
      setLoading(false);
    }
  };

  const getStatusBadge = (status) => {
    switch(status) {
      case 'scraping': return <span className="status-badge pulse-badge scraping">⚡ Scraping Page</span>;
      case 'downloading': return <span className="status-badge pulse-badge downloading">📥 Downloading</span>;
      case 'completed': return <span className="status-badge completed">✅ Completed</span>;
      case 'error': return <span className="status-badge error">❌ Failed</span>;
      default: return <span className="status-badge pulse-badge starting">⚙️ Initializing</span>;
    }
  };

  return (
    <main className="app-container">
      <section className="downloader-card" aria-label="Video Downloader Dashboard">
        <header className="card-header">
          <h1 className="title" id="app-title">Video Downloader Pro</h1>
          <p className="subtitle" id="app-subtitle">
            Simply <strong>paste a TikTok profile, Reddit Subreddit/post, Douyin video, Facebook Page/Reel, or Instagram link</strong>! Our automated engine seamlessly extracts <strong>100% of all videos</strong> into creator folders automatically.
          </p>
          <div className="platform-badges" aria-label="Supported Platforms">
            <span className="badge active-feature">⚡ TikTok (100% Profile Harvest)</span>
            <span className="badge active-feature">👽 Reddit (r/Subreddit Harvest)</span>
            <span className="badge">🇨🇳 Douyin (抖音)</span>
            <span className="badge">Facebook (Pages & Reels)</span>
            <span className="badge">Instagram (Profiles & Reels)</span>
          </div>
        </header>

        <div className="tip-box">
          <div className="tip-header">
            <span className="tip-icon">🚀</span>
            <strong>แค่วางลิงก์ก็โหลดครบ 100% ไม่ติดขีดจำกัด 10 คลิปอีกต่อไป!</strong>
          </div>
          <p className="tip-description">
            ระบบอัปเกรดใหม่: รองรับทั้ง <strong>TikTok, Reddit (ยกห้อง Subreddit เช่น r/videos หรือรายคลิป), Douyin, Facebook, Instagram</strong> ระบบจะดึงคลิปและแยกบันทึกโฟลเดอร์ตามชื่อช่องหรือชื่อ Subreddit (เช่น <code>VDO/r_videos/</code>) ให้อัตโนมัติครับ!
          </p>
        </div>

        <form className="download-form" id="download-form" onSubmit={handleDownload}>
          <div className="input-group">
            <label htmlFor="video-url-input" className="input-label">Video Link or Subreddit / Channel URL</label>
            <textarea
              id="video-url-input"
              className="url-input textarea-input"
              rows="3"
              placeholder="Paste link or text here (e.g. https://www.reddit.com/r/videos/, r/funny, TikTok, Douyin, Facebook, Instagram) and click download!"
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
                if (error) setError(null);
              }}
              disabled={loading}
              autoFocus
            />
          </div>

          <div className="download-type-selector" style={{ display: 'flex', gap: '15px', marginBottom: '15px', justifyContent: 'center' }}>
            <label onClick={() => !loading && setDownloadType('video')} style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', padding: '10px 20px', borderRadius: '8px', background: downloadType === 'video' ? 'var(--primary)' : 'rgba(255,255,255,0.05)', color: downloadType === 'video' ? 'white' : 'var(--text-secondary)', transition: 'all 0.2s ease', border: '1px solid', borderColor: downloadType === 'video' ? 'transparent' : 'rgba(255,255,255,0.1)' }}>
              <input type="radio" name="downloadType" value="video" checked={downloadType === 'video'} onChange={() => {}} disabled={loading} style={{ display: 'none' }} />
              🎬 Download Videos
            </label>
            <label onClick={() => !loading && setDownloadType('image')} style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', padding: '10px 20px', borderRadius: '8px', background: downloadType === 'image' ? 'var(--accent)' : 'rgba(255,255,255,0.05)', color: downloadType === 'image' ? 'white' : 'var(--text-secondary)', transition: 'all 0.2s ease', border: '1px solid', borderColor: downloadType === 'image' ? 'transparent' : 'rgba(255,255,255,0.1)' }}>
              <input type="radio" name="downloadType" value="image" checked={downloadType === 'image'} onChange={() => {}} disabled={loading} style={{ display: 'none' }} />
              🖼️ Download Images
            </label>
          </div>

          {downloadType === 'video' && (
            <div className="video-processing-panel" style={{
              background: 'rgba(15, 23, 42, 0.65)',
              border: '1px solid rgba(56, 189, 248, 0.2)',
              borderRadius: '16px',
              padding: '16px 20px',
              marginBottom: '20px',
              boxShadow: '0 4px 20px rgba(0, 0, 0, 0.25)'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                <span style={{ fontSize: '0.95rem', fontWeight: '600', color: '#38bdf8', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span>✨</span> ตัวเลือกแต่งวิดีโอ & กรณีศึกษางานวิจัย (Video Enhancements)
                </span>
                {(flip || brighten || (watermarkEnabled && watermarkText) || antiDetection) && (
                  <span style={{ fontSize: '0.75rem', background: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', padding: '2px 8px', borderRadius: '12px', border: '1px solid rgba(56, 189, 248, 0.3)' }}>
                    Active
                  </span>
                )}
              </div>

              {/* Anti-Algorithm Mode (Research Feature) */}
              <div style={{
                background: antiDetection ? 'linear-gradient(135deg, rgba(99, 102, 241, 0.18) 0%, rgba(168, 85, 247, 0.18) 100%)' : 'rgba(255, 255, 255, 0.02)',
                border: `1px solid ${antiDetection ? '#a855f7' : 'rgba(255, 255, 255, 0.08)'}`,
                borderRadius: '12px',
                padding: '12px 14px',
                marginBottom: '12px',
                transition: 'all 0.25s ease'
              }}>
                <label style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', cursor: 'pointer', userSelect: 'none' }}>
                  <input
                    type="checkbox"
                    checked={antiDetection}
                    onChange={(e) => setAntiDetection(e.target.checked)}
                    disabled={loading}
                    style={{ accentColor: '#a855f7', width: '18px', height: '18px', marginTop: '2px' }}
                  />
                  <div>
                    <div style={{ fontWeight: '600', fontSize: '0.9rem', color: antiDetection ? '#e9d5ff' : '#cbd5e1', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span>🛡️</span> โหมดหลบอัลกอริทึมขั้นสูง (Anti-Detection Suite 6 Layers)
                    </div>
                    <p style={{ fontSize: '0.78rem', color: '#94a3b8', margin: '4px 0 0 0', lineHeight: 1.4 }}>
                      กรณีศึกษางานวิจัย: ทำลาย Audio Spectrogram (+2% Speed) + Micro-Crop 3% + Noise Dithering + Gamma Shift เพื่อทดสอบความทนทานของ Facebook Rights Manager / Content ID
                    </p>
                  </div>
                </label>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '10px', marginBottom: watermarkEnabled ? '12px' : '0' }}>
                <label style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '10px 14px',
                  borderRadius: '10px',
                  background: (flip || antiDetection) ? 'rgba(56, 189, 248, 0.15)' : 'rgba(255, 255, 255, 0.03)',
                  border: `1px solid ${(flip || antiDetection) ? '#38bdf8' : 'rgba(255, 255, 255, 0.08)'}`,
                  cursor: antiDetection ? 'not-allowed' : 'pointer',
                  fontSize: '0.88rem',
                  userSelect: 'none',
                  transition: 'all 0.2s ease',
                  opacity: antiDetection ? 0.7 : 1
                }}>
                  <input
                    type="checkbox"
                    checked={flip || antiDetection}
                    onChange={(e) => !antiDetection && setFlip(e.target.checked)}
                    disabled={loading || antiDetection}
                    style={{ accentColor: '#06b6d4', width: '16px', height: '16px' }}
                  />
                  <span>🔄 กลับด้านวิดีโอ (Flip)</span>
                </label>

                <label style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '10px 14px',
                  borderRadius: '10px',
                  background: (brighten || antiDetection) ? 'rgba(56, 189, 248, 0.15)' : 'rgba(255, 255, 255, 0.03)',
                  border: `1px solid ${(brighten || antiDetection) ? '#38bdf8' : 'rgba(255, 255, 255, 0.08)'}`,
                  cursor: antiDetection ? 'not-allowed' : 'pointer',
                  fontSize: '0.88rem',
                  userSelect: 'none',
                  transition: 'all 0.2s ease',
                  opacity: antiDetection ? 0.7 : 1
                }}>
                  <input
                    type="checkbox"
                    checked={brighten || antiDetection}
                    onChange={(e) => !antiDetection && setBrighten(e.target.checked)}
                    disabled={loading || antiDetection}
                    style={{ accentColor: '#06b6d4', width: '16px', height: '16px' }}
                  />
                  <span>☀️ เพิ่มแสงเล็กน้อย</span>
                </label>

                <label style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '10px 14px',
                  borderRadius: '10px',
                  background: watermarkEnabled ? 'rgba(56, 189, 248, 0.15)' : 'rgba(255, 255, 255, 0.03)',
                  border: `1px solid ${watermarkEnabled ? '#38bdf8' : 'rgba(255, 255, 255, 0.08)'}`,
                  cursor: 'pointer',
                  fontSize: '0.88rem',
                  userSelect: 'none',
                  transition: 'all 0.2s ease'
                }}>
                  <input
                    type="checkbox"
                    checked={watermarkEnabled}
                    onChange={(e) => setWatermarkEnabled(e.target.checked)}
                    disabled={loading}
                    style={{ accentColor: '#06b6d4', width: '16px', height: '16px' }}
                  />
                  <span>🏷️ ใส่ลายน้ำข้อความ</span>
                </label>
              </div>

              {watermarkEnabled && (
                <div style={{
                  marginTop: '12px',
                  paddingTop: '12px',
                  borderTop: '1px solid rgba(255, 255, 255, 0.06)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '10px'
                }}>
                  <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                    <input
                      type="text"
                      placeholder="พิมพ์ข้อความลายน้ำ เช่น ชื่อช่อง / @Channel"
                      value={watermarkText}
                      onChange={(e) => setWatermarkText(e.target.value)}
                      disabled={loading}
                      style={{
                        flex: 1,
                        padding: '8px 12px',
                        borderRadius: '8px',
                        background: 'rgba(0, 0, 0, 0.3)',
                        border: '1px solid rgba(255, 255, 255, 0.15)',
                        color: '#fff',
                        fontSize: '0.88rem'
                      }}
                    />
                    <select
                      value={watermarkPosition}
                      onChange={(e) => setWatermarkPosition(e.target.value)}
                      disabled={loading}
                      style={{
                        padding: '8px 12px',
                        borderRadius: '8px',
                        background: '#0f172a',
                        border: '1px solid rgba(255, 255, 255, 0.15)',
                        color: '#fff',
                        fontSize: '0.85rem'
                      }}
                    >
                      <option value="bottom_right">มุมล่างขวา</option>
                      <option value="center">กึ่งกลางคลิป</option>
                      <option value="top_right">มุมบนขวา</option>
                      <option value="bottom_left">มุมล่างซ้าย</option>
                    </select>
                  </div>

                  {/* Watermark Opacity Slider */}
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    background: 'rgba(0, 0, 0, 0.25)',
                    padding: '8px 12px',
                    borderRadius: '8px',
                    border: '1px solid rgba(255, 255, 255, 0.06)'
                  }}>
                    <span style={{ fontSize: '0.8rem', color: '#94a3b8', minWidth: '135px' }}>
                      ความโปร่งแสง (Opacity): <strong style={{ color: '#38bdf8' }}>{Math.round(watermarkOpacity * 100)}%</strong>
                    </span>
                    <input
                      type="range"
                      min="0.10"
                      max="1.0"
                      step="0.05"
                      value={watermarkOpacity}
                      onChange={(e) => setWatermarkOpacity(parseFloat(e.target.value))}
                      disabled={loading}
                      style={{ flex: 1, accentColor: '#38bdf8', cursor: 'pointer' }}
                    />
                    <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                      {watermarkOpacity <= 0.3 ? 'เนียนตาไม่รบกวน' : watermarkOpacity <= 0.6 ? 'โปร่งแสงปานกลาง' : 'ชัดเจน'}
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}

          <button 
            type="submit" 
            id="download-button"
            className="submit-button" 
            disabled={loading}
          >
            {loading ? (
              <>
                <span className="spinner" aria-hidden="true"></span>
                <span>Extracting & Downloading All Clips...</span>
              </>
            ) : (
              <span>⚡ Paste Link & Download All Videos</span>
            )}
          </button>
        </form>

        {error && (
          <div className="status-message error-card" role="alert" id="error-display">
            <span className="status-icon" aria-hidden="true">⚠️</span>
            <div>
              <strong>Error:</strong> {error}
            </div>
          </div>
        )}

        {activeJob && (
          <div className={`job-card ${activeJob.status}`} role="status" id="job-status-display">
            <header className="job-header">
              <div className="job-title-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <h3>Live Activity Monitor</h3>
                  {getStatusBadge(activeJob.status)}
                </div>
                <button 
                  type="button" 
                  onClick={handleResetJob}
                  style={{
                    background: 'rgba(255, 255, 255, 0.08)',
                    border: '1px solid rgba(255, 255, 255, 0.2)',
                    color: '#cbd5e1',
                    padding: '5px 14px',
                    borderRadius: '8px',
                    fontSize: '0.8rem',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '5px',
                    transition: 'all 0.2s ease'
                  }}
                  title="Clear view and start a new download"
                >
                  <span>🔄</span> เริ่มใหม่ / โหลดลิงก์อื่น
                </button>
              </div>
              <p className="job-message">{activeJob.progress_message}</p>
            </header>

            {activeJob.status === 'scraping' && (
              <div style={{
                margin: '14px 0',
                padding: '12px 16px',
                background: 'rgba(56, 189, 248, 0.1)',
                border: '1px solid rgba(56, 189, 248, 0.3)',
                borderRadius: '10px',
                display: 'flex',
                alignItems: 'center',
                gap: '12px'
              }}>
                <span style={{ fontSize: '1.4rem' }}>⚡</span>
                <div>
                  <div style={{ fontWeight: '600', color: '#38bdf8', fontSize: '0.88rem' }}>
                    กำลังเลื่อนสแกนหน้าเพจเพื่อค้นหาคลิปทั้งหมด (Deep Harvesting)...
                  </div>
                  <div style={{ fontSize: '0.78rem', color: '#94a3b8' }}>
                    ระบบกำลังเลื่อนหน้าจออัตโนมัติเพื่อดึงลิงก์ Reels ทั้งหมดให้ครบ โปรดรอสักครู่
                  </div>
                </div>
              </div>
            )}

            {activeJob.total_videos > 0 && (
              <div className="progress-section">
                <div className="progress-bar-bg">
                  <div 
                    className="progress-bar-fill" 
                    style={{ 
                      width: `${activeJob.status === 'completed' ? 100 : Math.min(100, Math.round(((activeJob.current_index || activeJob.completed_videos) / activeJob.total_videos) * 100))}%`,
                      transition: 'width 0.4s ease'
                    }}
                  ></div>
                </div>
                <div className="progress-stats">
                  <span>Folder: <strong>{activeJob.items && activeJob.items.some(i => i.rel_path && i.rel_path.startsWith('VDO_processed')) ? 'VDO_processed' : 'VDO'}/{activeJob.page_name || 'General_Clips'}</strong></span>
                  <span>
                    {activeJob.status === 'completed' 
                      ? `✅ ${activeJob.completed_videos} clips saved (${activeJob.total_videos} total scanned)`
                      : `Checking ${activeJob.current_index || activeJob.completed_videos} of ${activeJob.total_videos} (${activeJob.completed_videos} saved)`}
                  </span>
                </div>
              </div>
            )}

            {activeJob.items && activeJob.items.length > 0 && (
              <div className="downloaded-items-container">
                <h4>
                  {activeJob.items.some(i => i.rel_path && i.rel_path.startsWith('VDO_processed')) 
                    ? '✨ Processed & Flipped Videos (Folder: VDO_processed)' 
                    : 'Saved Files in Folder'}
                </h4>
                <ul className="items-list">
                  {activeJob.items.map((item, index) => (
                    <li key={index} className="download-item">
                      <div className="item-info">
                        <span className="file-icon">🎬</span>
                        <span className="file-name" title={item.filename}>{item.title || item.filename}</span>
                      </div>
                      <a 
                        href={`${API_BASE_URL}${item.download_url}`} 
                        download={item.filename} 
                        className="btn-download-file"
                        target="_blank" 
                        rel="noopener noreferrer"
                      >
                        Download File
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        <footer className="footer-info">
          <p>✨ Original raw downloads are stored in <code>VDO</code>. Flipped, enhanced, and watermark-protected videos are stored in <code>VDO_processed</code>.</p>
        </footer>
      </section>
    </main>
  );
}

export default App;
