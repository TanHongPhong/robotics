import { useEffect, useRef } from 'react';
import './Camera.css';

export default function Camera() {
    const videoRef = useRef(null);

    useEffect(() => {
        async function initCamera() {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ video: true });
                if (videoRef.current) {
                    videoRef.current.srcObject = stream;
                }
            } catch (err) {
                console.log("Camera unavailable:", err);
            }
        }

        initCamera();

        return () => {
            if (videoRef.current && videoRef.current.srcObject) {
                const tracks = videoRef.current.srcObject.getTracks();
                tracks.forEach(track => track.stop());
            }
        };
    }, []);

    return (
        <div className="camera-section">
            <span className="section-title">Live Vision Feed</span>
            <div className="camera-wrapper">
                <video ref={videoRef} id="webcam" autoPlay playsInline muted></video>
                <div className="camera-overlay">
                    OBJECT DETECTION ACTIVE
                </div>
            </div>
        </div>
    );
}
