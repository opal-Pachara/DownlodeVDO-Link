import React, { useState, useEffect, useRef } from 'react';
import './index.css';

const SUPPORTED_DOMAINS = [
  'youtube.com',
  'youtu.be',
  'tiktok.com',
  'facebook.com',
  'fb.watch',
  'instagram.com'
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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeJob, setActiveJob] = useState(null);
  const pollingIntervalRef = useRef(null);

  const validateUrl = (targetUrl) => {
    if (!targetUrl || !targetUrl.trim()) {
      return { valid: false, error: 'Please enter a valid video link, channel page URL, or copied page text.' };
    }
    
    const text = targetUrl.trim().toLowerCase();
    const hasSupportedKeyword = SUPPORTED_DOMAINS.some(domain => text.includes(domain));
    if (hasSupportedKeyword) {
      return { valid: true };
    }
    
    return { 
      valid: false, 
      error: 'Unsupported content. Please paste a valid web link or copied text from YouTube, TikTok, Facebook (Reels/Pages), or Instagram.' 
    };
  };

  const clearPolling = () => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
  };

  useEffect(() => {
    if (activeJob && !['completed', 'error'].includes(activeJob.status)) {
      pollingIntervalRef.current = setInterval(async () => {
        try {
          const res = await fetch(`${API_BASE_URL}/jobs/${activeJob.id}`);
          if (res.ok) {
            const jobData = await res.json();
            setActiveJob(jobData);
            if (['completed', 'error'].includes(jobData.status)) {
              clearPolling();
              setLoading(false);
              if (jobData.status === 'error') {
                setError(jobData.error || 'Job failed during downloading.');
              }
            }
          }
        } catch (err) {
          console.error("Error polling job status:", err);
        }
      }, 1500);
    } else {
      clearPolling();
    }

    return () => clearPolling();
  }, [activeJob?.id, activeJob?.status]);

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
        body: JSON.stringify({ url: url.trim(), download_type: downloadType }),
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
            Simply <strong>paste a video, playlist, or Facebook Page link</strong>! Our Auto-Cookie technology seamlessly extracts <strong>100% of all videos on any channel</strong> into creator folders automatically.
          </p>
          <div className="platform-badges" aria-label="Supported Platforms">
            <span className="badge">YouTube (Channels & Playlists)</span>
            <span className="badge">TikTok (Profiles)</span>
            <span className="badge active-feature">⚡ Auto-Cookie 100% Facebook Page Download</span>
            <span className="badge">Instagram</span>
          </div>
        </header>

        <div className="tip-box">
          <div className="tip-header">
            <span className="tip-icon">🚀</span>
            <strong>แค่วางลิงก์ก็โหลดครบ 100% ไม่ติดขีดจำกัด 10 คลิปอีกต่อไป!</strong>
          </div>
          <p className="tip-description">
            ระบบอัปเกรดใหม่ <strong>Auto-Cookie Sync</strong>: เมื่อคุณวางลิงก์หน้าเพจ Facebook (เช่น ลิงก์ช่อง Reels) ระบบหลังบ้านจะทำการดึงการเข้าถึงจากเบราว์เซอร์ Google Chrome ของคุณโดยอัตโนมัติ เพื่อสกรอลและดูดคลิปออกมา <strong>ครบทุกคลิปทั้งเพจ (100+ คลิป)</strong> แยกลงโฟลเดอร์ให้เองตามชื่อช่องครับ!
          </p>
        </div>

        <form className="download-form" id="download-form" onSubmit={handleDownload}>
          <div className="input-group">
            <label htmlFor="video-url-input" className="input-label">Video Link or Facebook Page / Reels URL</label>
            <textarea
              id="video-url-input"
              className="url-input textarea-input"
              rows="3"
              placeholder="Paste a single link here (e.g., https://www.facebook.com/profile.php?id=...&sk=reels_tab) and click download!"
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
              <div className="job-title-row">
                <h3>Live Activity Monitor</h3>
                {getStatusBadge(activeJob.status)}
              </div>
              <p className="job-message">{activeJob.progress_message}</p>
            </header>

            {activeJob.total_videos > 0 && (
              <div className="progress-section">
                <div className="progress-bar-bg">
                  <div 
                    className="progress-bar-fill" 
                    style={{ width: `${Math.min(100, (activeJob.completed_videos / activeJob.total_videos) * 100)}%` }}
                  ></div>
                </div>
                <div className="progress-stats">
                  <span>Folder: <strong>VDO/{activeJob.page_name || 'General_Clips'}</strong></span>
                  <span>{activeJob.completed_videos} of {activeJob.total_videos} clips saved</span>
                </div>
              </div>
            )}

            {activeJob.items && activeJob.items.length > 0 && (
              <div className="downloaded-items-container">
                <h4>Saved Files in Folder (VDO/{activeJob.page_name || 'Clips'})</h4>
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
          <p>✨ Automated via open-source tools. All videos are organized automatically into subfolders by creator name inside the <code>VDO</code> directory.</p>
        </footer>
      </section>
    </main>
  );
}

export default App;
