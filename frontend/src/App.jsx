import React, { useState } from 'react';
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
  if (import.meta.env.PROD) return ''; // In production Docker bundle, API and static UI share the exact same host & port!
  const hostname = window.location.hostname || '127.0.0.1';
  return `http://${hostname}:8000`;
};
const API_BASE_URL = getApiBaseUrl();

function App() {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);

  const validateUrl = (targetUrl) => {
    if (!targetUrl || !targetUrl.trim()) {
      return { valid: false, error: 'Please enter a video URL.' };
    }
    
    try {
      const parsed = new URL(targetUrl.trim());
      if (!parsed.protocol.startsWith('http')) {
        return { valid: false, error: 'URL must start with http:// or https://.' };
      }
      
      let hostname = parsed.hostname.toLowerCase();
      if (hostname.startsWith('www.')) hostname = hostname.slice(4);
      if (hostname.startsWith('m.')) hostname = hostname.slice(2);
      if (hostname.startsWith('l.facebook.com') || hostname.startsWith('l.instagram.com')) hostname = hostname.slice(2);
      
      const matched = SUPPORTED_DOMAINS.some(
        domain => hostname === domain || hostname.endsWith(`.${domain}`)
      );
      
      if (!matched) {
        return { 
          valid: false, 
          error: 'Unsupported platform domain. Supported sites: YouTube, TikTok, Facebook, Instagram.' 
        };
      }

      return { valid: true };
    } catch {
      return { valid: false, error: 'Invalid URL format. Please paste a full web link.' };
    }
  };

  const handleDownload = async (e) => {
    e.preventDefault();
    setError(null);
    setSuccessMsg(null);

    const check = validateUrl(url);
    if (!check.valid) {
      setError(check.error);
      return;
    }

    setLoading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/download`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ url: url.trim() }),
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

      setSuccessMsg(`Successfully saved "${data.filename}" directly to the VDO folder!`);
      setUrl(''); // Clear input after success as requested
    } catch (err) {
      setError(err.message || 'Network error occurred while connecting to the download server.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="app-container">
      <section className="downloader-card" aria-label="Video Downloader Dashboard">
        <header className="card-header">
          <h1 className="title" id="app-title">Video Downloader</h1>
          <p className="subtitle" id="app-subtitle">Paste a video link below to download instantly in high quality.</p>
          <div className="platform-badges" aria-label="Supported Platforms">
            <span className="badge">YouTube</span>
            <span className="badge">TikTok</span>
            <span className="badge">Facebook</span>
            <span className="badge">Instagram</span>
          </div>
        </header>

        <form className="download-form" id="download-form" onSubmit={handleDownload}>
          <div className="input-group">
            <label htmlFor="video-url-input" className="input-label">Video URL</label>
            <input
              id="video-url-input"
              type="url"
              className="url-input"
              placeholder="https://www.youtube.com/watch?v=..."
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
                if (error) setError(null);
                if (successMsg) setSuccessMsg(null);
              }}
              disabled={loading}
              autoFocus
              autoComplete="off"
            />
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
                <span>Downloading Video...</span>
              </>
            ) : (
              <span>Download</span>
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

        {successMsg && (
          <div className="status-message success-card" role="status" id="success-display">
            <span className="status-icon" aria-hidden="true">✓</span>
            <div>
              <strong>Success:</strong> {successMsg}
            </div>
          </div>
        )}

        <footer className="footer-info">
          <p>All downloaded clips are saved directly into the VDO folder.</p>
        </footer>
      </section>
    </main>
  );
}

export default App;
