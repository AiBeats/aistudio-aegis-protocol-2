/**
 * ABV Sovereign Stack — Decoy Nuclear Screen
 *
 * Displays a convincing fake BSOD / Windows Update screen to mask
 * the silent purge sequence running in the background.  Designed
 * to buy time during a nuke-finger or scorched earth event.
 */

import React, { useState, useEffect, useCallback } from 'react';

/** Slowly incrementing "progress" percentage for realism */
function useSlowProgress(initialValue = 21, maxValue = 99, intervalMs = 3000) {
  const [progress, setProgress] = useState(initialValue);

  useEffect(() => {
    const timer = setInterval(() => {
      setProgress((prev) => {
        if (prev >= maxValue) return prev;
        // Random small increment for realism
        const increment = Math.floor(Math.random() * 3) + 1;
        return Math.min(prev + increment, maxValue);
      });
    }, intervalMs);

    return () => clearInterval(timer);
  }, [maxValue, intervalMs]);

  return progress;
}

/** Cycling status messages */
const STATUS_MESSAGES = [
  'Installing update 1 of 3...',
  'Configuring Windows features...',
  'Applying changes...',
  'Installing update 2 of 3...',
  'Preparing to configure Windows...',
  'Installing update 3 of 3...',
  'Finalizing installation...',
  'Cleaning up temporary files...',
];

function useCyclingStatus(intervalMs = 8000) {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setIndex((prev) => (prev + 1) % STATUS_MESSAGES.length);
    }, intervalMs);

    return () => clearInterval(timer);
  }, [intervalMs]);

  return STATUS_MESSAGES[index];
}

/**
 * DecoyNuclearScreen — Full-screen BSOD/update decoy.
 *
 * Props:
 *   onPurgeComplete - Optional callback when the decoy should dismiss
 *   variant         - "bsod" or "update" (default: "update")
 */
const DecoyNuclearScreen = ({ onPurgeComplete, variant = 'update' }) => {
  const progress = useSlowProgress(21, 99, 3000);
  const statusText = useCyclingStatus(8000);

  // Prevent all keyboard shortcuts
  const blockInput = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    return false;
  }, []);

  useEffect(() => {
    // Block keyboard
    document.addEventListener('keydown', blockInput, true);
    document.addEventListener('keyup', blockInput, true);

    // Block right-click
    document.addEventListener('contextmenu', blockInput, true);

    // Hide cursor
    document.body.style.cursor = 'none';

    // Request fullscreen
    try {
      document.documentElement.requestFullscreen?.();
    } catch {
      // Fullscreen may not be available
    }

    return () => {
      document.removeEventListener('keydown', blockInput, true);
      document.removeEventListener('keyup', blockInput, true);
      document.removeEventListener('contextmenu', blockInput, true);
      document.body.style.cursor = 'default';
    };
  }, [blockInput]);

  if (variant === 'bsod') {
    return <BSODScreen />;
  }

  return <UpdateScreen progress={progress} statusText={statusText} />;
};

/** Windows Update decoy screen */
const UpdateScreen = ({ progress, statusText }) => (
  <div style={styles.container}>
    <div style={styles.content}>
      <div style={styles.spinner}>
        <div style={styles.spinnerCircle} />
      </div>
      <div style={styles.title}>Working on updates</div>
      <div style={styles.progress}>{progress}% complete</div>
      <div style={styles.subtitle}>{statusText}</div>
      <div style={styles.warning}>
        Don't turn off your PC. This will take a while.
      </div>
      <div style={styles.warning}>
        Your PC will restart several times.
      </div>
    </div>
  </div>
);

/** Blue Screen of Death decoy */
const BSODScreen = () => (
  <div style={styles.bsodContainer}>
    <div style={styles.bsodContent}>
      <div style={styles.sadFace}>:(</div>
      <div style={styles.bsodTitle}>
        Your PC ran into a problem and needs to restart. We're just
        collecting some error info, and then we'll restart for you.
      </div>
      <div style={styles.bsodProgress}>0% complete</div>
      <div style={styles.bsodDetails}>
        <br />
        For more information about this issue and possible fixes, visit
        <br />
        https://www.windows.com/stopcode
        <br />
        <br />
        If you call a support person, give them this info:
        <br />
        Stop code: CRITICAL_PROCESS_DIED
      </div>
      <div style={styles.bsodQr}>
        {/* QR code placeholder - in production, render a fake QR */}
        <div style={styles.qrPlaceholder} />
      </div>
    </div>
  </div>
);

/** Styles — inline to avoid external CSS dependencies */
const styles = {
  // Windows Update screen
  container: {
    position: 'fixed',
    top: 0,
    left: 0,
    width: '100vw',
    height: '100vh',
    backgroundColor: '#0078D4',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 999999,
    fontFamily: 'Segoe UI, Tahoma, Geneva, Verdana, sans-serif',
    userSelect: 'none',
  },
  content: {
    textAlign: 'center',
    color: '#ffffff',
    maxWidth: '600px',
  },
  spinner: {
    marginBottom: '40px',
    display: 'flex',
    justifyContent: 'center',
  },
  spinnerCircle: {
    width: '60px',
    height: '60px',
    border: '4px solid rgba(255, 255, 255, 0.3)',
    borderTop: '4px solid #ffffff',
    borderRadius: '50%',
    animation: 'spin 1.5s linear infinite',
  },
  title: {
    fontSize: '28px',
    fontWeight: '300',
    marginBottom: '20px',
    letterSpacing: '0.5px',
  },
  progress: {
    fontSize: '48px',
    fontWeight: '200',
    marginBottom: '20px',
  },
  subtitle: {
    fontSize: '14px',
    fontWeight: '300',
    marginBottom: '10px',
    opacity: 0.9,
  },
  warning: {
    fontSize: '12px',
    fontWeight: '300',
    opacity: 0.7,
    marginTop: '5px',
  },

  // BSOD screen
  bsodContainer: {
    position: 'fixed',
    top: 0,
    left: 0,
    width: '100vw',
    height: '100vh',
    backgroundColor: '#0078D7',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'flex-start',
    paddingLeft: '10%',
    zIndex: 999999,
    fontFamily: 'Segoe UI, Tahoma, Geneva, Verdana, sans-serif',
    userSelect: 'none',
  },
  bsodContent: {
    color: '#ffffff',
    maxWidth: '700px',
  },
  sadFace: {
    fontSize: '120px',
    fontWeight: '100',
    marginBottom: '20px',
  },
  bsodTitle: {
    fontSize: '22px',
    fontWeight: '300',
    lineHeight: '1.5',
    marginBottom: '20px',
  },
  bsodProgress: {
    fontSize: '22px',
    fontWeight: '300',
    marginBottom: '30px',
  },
  bsodDetails: {
    fontSize: '12px',
    fontWeight: '300',
    lineHeight: '1.8',
    opacity: 0.9,
  },
  bsodQr: {
    marginTop: '20px',
  },
  qrPlaceholder: {
    width: '80px',
    height: '80px',
    backgroundColor: 'rgba(255, 255, 255, 0.2)',
    display: 'inline-block',
  },
};

/** Inject keyframe animation for spinner */
if (typeof document !== 'undefined') {
  const styleSheet = document.createElement('style');
  styleSheet.textContent = `
    @keyframes spin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
  `;
  document.head.appendChild(styleSheet);
}

export default DecoyNuclearScreen;
