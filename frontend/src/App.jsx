import { useState, useMemo, useEffect } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import FaultyTerminal from "./Faulty";
import { Link, Upload, FileImage } from "lucide-react";
import { InstagramEmbed, TikTokEmbed } from "react-social-media-embed";

const API_BASE_URL = import.meta.env.VITE_API_URL;

const FakeReelPlayer = ({ url, verdict }) => {
  const getPlatform = (link) => {
    if (!link) return "unknown";
    if (link.includes("instagram.com")) return "instagram";
    if (link.includes("tiktok.com")) return "tiktok";
    if (link.includes("youtube") || link.includes("youtu.be")) return "youtube";
    return "unknown";
  };

  const getYoutubeEmbed = (link) => {
    try {
      let videoId = "";
      if (link.includes("/shorts/")) {
        videoId = link.split("/shorts/")[1].split("?")[0];
      } else if (link.includes("v=")) {
        videoId = link.split("v=")[1].split("&")[0];
      } else if (link.includes("youtu.be/")) {
        videoId = link.split("youtu.be/")[1].split("?")[0];
      }

      if (videoId) {
        return `https://www.youtube.com/embed/${videoId}?autoplay=1&mute=1&controls=0&loop=1&playlist=${videoId}&modestbranding=1&rel=0`;
      }
    } catch (e) {
      console.error("YT Parse Error", e);
    }
    return null;
  };

  const platform = getPlatform(url);
  const youtubeSrc = platform === "youtube" ? getYoutubeEmbed(url) : null;

  const isFake = verdict?.verdict === "FAKE";
  const color = isFake
    ? "red"
    : verdict?.verdict === "REAL"
    ? "green"
    : "yellow";
  const borderColor = isFake
    ? "border-red-600"
    : verdict?.verdict === "REAL"
    ? "border-green-600"
    : "border-yellow-600";

  return (
    <div
      className={`relative w-[320px] h-[580px] flex-shrink-0 rounded-3xl overflow-hidden border-4 ${borderColor} shadow-[0_0_50px_rgba(0,0,0,0.6)] bg-black`}
    >
      {/* VIDEO LAYER */}
      <div className="absolute inset-0 z-0 bg-gray-900 flex items-center justify-center">
        {/* YOUTUBE */}
        {platform === "youtube" && youtubeSrc && (
          <iframe
            width="100%"
            height="100%"
            src={youtubeSrc}
            className="w-full h-full object-cover scale-[1.35]"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            frameBorder="0"
          ></iframe>
        )}

        {/* INSTAGRAM */}
        {platform === "instagram" && (
          <div className="scale-[0.85] origin-top -mt-2">
            <InstagramEmbed url={url} width={328} captioned />
          </div>
        )}

        {/* TIKTOK */}
        {platform === "tiktok" && (
          <div className="scale-[0.85] origin-top -mt-2">
            <TikTokEmbed url={url} width={325} />
          </div>
        )}

        {/* FALLBACK / UNKNOWN */}
        {(platform === "unknown" ||
          (platform === "youtube" && !youtubeSrc)) && (
          <div className="text-gray-500 text-xs p-4 text-center">
            Preview Unavailable.
            <br />
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="text-green-500 underline"
            >
              Open Link
            </a>
          </div>
        )}
      </div>

      {/* OVERLAY LAYER */}
      <div className="absolute inset-0 z-10 flex flex-col justify-between p-6 bg-gradient-to-b from-black/60 via-transparent to-black/90 pointer-events-none">
        {/* HEADER */}
        <div className="flex justify-between items-center">
          <span className="text-[10px] font-mono text-green-500 bg-green-900/30 border border-green-500 px-2 py-0.5 rounded backdrop-blur-md">
            SHIN_VISION
          </span>
          <div
            className={`w-2 h-2 rounded-full animate-pulse bg-${color}-500 shadow-[0_0_10px_${color}]`}
          ></div>
        </div>

        {/* VERDICT STAMP */}
        <div className="flex flex-col gap-2">
          <h1
            className={`text-5xl font-black italic tracking-tighter text-${color}-500 -rotate-6 opacity-90 drop-shadow-2xl`}
          >
            {verdict?.verdict || "ANALYZING"}
          </h1>
          <div className="h-1 w-full bg-gray-700 rounded-full overflow-hidden mt-2 backdrop-blur-sm">
            <div
              className={`h-full bg-${color}-500 transition-all duration-1000`}
              style={{ width: `${verdict?.confidence_score || 0}%` }}
            ></div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default function App() {
  const [url, setUrl] = useState("");
  const [claim, setClaim] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [mode, setMode] = useState("url");
  const [file, setFile] = useState(null);
  const [logs, setLogs] = useState([]);

  const terminalBackground = useMemo(
    () => (
      <FaultyTerminal
        scale={1.5}
        gridMul={[2, 1]}
        digitSize={2}
        timeScale={1}
        pause={false}
        scanlineIntensity={1}
        glitchAmount={1}
        flickerAmount={1}
        noiseAmp={1}
        chromaticAberration={0}
        dither={0}
        curvature={0}
        tint="#a7ef9e"
        mouseReact={true}
        mouseStrength={0.5}
        pageLoadAnimation={false}
        brightness={1}
      />
    ),
    []
  );

 const handleInvestigate = async () => {
   if (mode === "url" && !url && !claim) {
     alert("Please provide a URL or a Claim.");
     return;
   }
   if (mode === "upload" && !file && !claim) {
     alert("Please upload a file or provide a Claim.");
     return;
   }

   setLoading(true);
   setLogs([]);
   setResult(null);

   try {
     const headers =
       mode === "upload" ? {} : { "Content-Type": "application/json" };
     const body =
       mode === "upload"
         ? (() => {
             const fd = new FormData();
             fd.append("file", file);
             fd.append("claim_text", claim);
             return fd;
           })()
         : JSON.stringify({ image_url: url, claim_text: claim });

     const response = await fetch(`${API_BASE_URL}/investigate`, {
       method: "POST",
       headers: headers,
       body: body,
     });

     const reader = response.body.getReader();
     const decoder = new TextDecoder();
     let buffer = ""; // <--- NEW: Buffer to hold split chunks

     while (true) {
       const { done, value } = await reader.read();
       if (done) break;

       // Append new chunk to buffer
       buffer += decoder.decode(value, { stream: true });

       // Process complete lines only
       const lines = buffer.split("\n");

       // Keep the last part in the buffer (it might be incomplete)
       buffer = lines.pop();

       for (const line of lines) {
         if (!line.trim()) continue;
         try {
           const data = JSON.parse(line);

           if (data.type === "log") {
             setLogs((prev) => [...prev, `[${data.agent}] ${data.message}`]);
           } else if (data.type === "result") {
             console.log("FINAL RESULT:", data);
             setResult({
               final_verdict: data.final_verdict,
               swarm_logs: data.swarm_logs,
               auto_claim: data.auto_claim,
               is_video: data.is_video,
             });
           } else if (data.type === "ping") {
             // Ignore keep-alive pings
           }
         } catch (e) {
           console.error("JSON Parse Error (ignoring):", e);
         }
       }
     }
   } catch (error) {
     console.error("Stream Error:", error);
     // Don't alert immediately, check logs first
   }
   setLoading(false);
 };
  return (
    <div className="w-full h-screen">
      <div className="w-full h-screen absolute inset-0 z-0 ">
        {terminalBackground}
      </div>
      <div className="items-center bg-black/60 w-full h-screen justify-center flex flex-col gap-8 relative z-10">
        <header className="text-center border-b border-gray-800 pb-6">
          <h1 className="text-4xl font-bold tracking-tighter text-green-500">
            SHIN PROTOCOL
          </h1>
          <p className="text-xs text-white mt-2">
            AUTONOMOUS TRUTH ENGINE v1.0
          </p>
        </header>

        {/* INPUT SECTION */}
        {!result && !loading && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex w-1/3 flex-col gap-4"
          >
            {/* TOGGLE BUTTONS */}
            <div className="flex gap-4 justify-center mb-2">
              <button
                onClick={() => setMode("url")}
                className={`flex items-center gap-2 px-4 py-2 rounded text-sm transition-all ${
                  mode === "url"
                    ? "bg-green-600 text-black font-bold shadow-[0_0_10px_#00ff41]"
                    : "bg-gray-900 border border-gray-700 text-gray-500 hover:text-white"
                }`}
              >
                <Link size={16} /> Paste Link
              </button>
              <button
                onClick={() => setMode("upload")}
                className={`flex items-center gap-2 px-4 py-2 rounded text-sm transition-all ${
                  mode === "upload"
                    ? "bg-green-600 text-black font-bold shadow-[0_0_10px_#00ff41]"
                    : "bg-gray-900 border border-gray-700 text-gray-500 hover:text-white"
                }`}
              >
                <Upload size={16} /> Upload File
              </button>
            </div>

            {/* CONDITIONAL INPUT: URL OR FILE */}
            {mode === "url" ? (
              <input
                className="bg-gray-900 border border-gray-700 p-4 rounded text-green-400 focus:outline-none focus:border-green-500 font-mono"
                placeholder="Paste URL..."
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            ) : (
              <div className="relative">
                <input
                  type="file"
                  id="file-upload"
                  accept="image/*"
                  onChange={(e) => setFile(e.target.files[0])}
                  className="hidden"
                />
                <label
                  htmlFor="file-upload"
                  className="flex items-center justify-center gap-3 bg-gray-900 border border-dashed border-gray-600 p-4 rounded cursor-pointer hover:bg-gray-800 hover:border-green-500 transition-all group"
                >
                  <FileImage className="text-gray-500 group-hover:text-green-400" />
                  <span className="text-gray-400 group-hover:text-white">
                    {file ? file.name : "Click to Upload Evidence"}
                  </span>
                </label>
              </div>
            )}

            {/* CLAIM INPUT (ALWAYS VISIBLE) */}
            <input
              className="bg-gray-900 border border-gray-700 p-4 rounded text-white focus:outline-none focus:border-green-500"
              placeholder="What is the claim? (Leave empty to Auto-Detect)"
              value={claim}
              onChange={(e) => setClaim(e.target.value)}
            />

            <button
              onClick={handleInvestigate}
              className="bg-green-600 hover:bg-[#282828] text-black hover:text-white font-bold py-4 rounded transition-all glow-border"
            >
              INITIATE SWARM
            </button>
          </motion.div>
        )}

        {/* LOADING STATE (REAL-TIME TERMINAL) */}
        {loading && (
          <div className="border w-1/3 border-green-900 bg-black p-6 rounded font-mono text-sm h-[33vh] overflow-hidden relative shadow-[0_0_20px_rgba(0,255,0,0.2)]">
            <div className="scan-line absolute top-0 left-0"></div>
            <div className="flex flex-col gap-2 h-full overflow-y-auto pb-4 scrollbar-hide">
              <p className="text-green-500">
                [SYSTEM] Initializing Swarm Protocol...
              </p>
              {logs.map((log, index) => (
                <p
                  key={index}
                  className="text-green-400 font-mono text-xs animate-pulse"
                >
                  {log}
                </p>
              ))}
              <p className="text-gray-500 animate-pulse">_</p>
            </div>
          </div>
        )}

        {/* RESULT SECTION */}
        {result && (
          <motion.div
            initial={{ scale: 0.9 }}
            animate={{ scale: 1 }}
            className="flex flex-col gap-6 w-3/4 max-w-6xl"
          >
            {/* CONTAINER: REEL + INFO */}
            <div className="w-full flex flex-row gap-10 justify-center">
              {/* REEL PLAYER (Left) */}
              {result.is_video && (
                <FakeReelPlayer url={url} verdict={result.final_verdict} />
              )}

              {/* REPORT CARD (Right) */}
              <div
                className={`flex-1 p-8 border-4 text-center rounded-xl backdrop-blur-md transition-all duration-500 flex flex-col justify-center ${
                  result.final_verdict?.verdict === "FAKE"
                    ? "border-red-600 bg-red-900/40 shadow-[0_0_50px_rgba(255,0,0,0.4)]"
                    : result.final_verdict?.verdict === "REAL"
                    ? "border-green-600 bg-green-900/40 shadow-[0_0_50px_rgba(0,255,0,0.4)]"
                    : "border-yellow-600 bg-yellow-900/40"
                }`}
              >
                <h2
                  className={`text-6xl font-black tracking-widest ${
                    result.final_verdict?.verdict === "FAKE"
                      ? "text-red-500"
                      : result.final_verdict?.verdict === "REAL"
                      ? "text-green-500"
                      : "text-yellow-500"
                  }`}
                >
                  {result.final_verdict?.verdict}
                </h2>
                <p className="mt-4 text-white text-lg font-mono leading-relaxed text-left">
                  {result.final_verdict?.summary}
                </p>

                {/* CONFIDENCE METER */}
                <div className="mt-8 text-left">
                  <div className="flex justify-between text-xs font-mono text-gray-400 mb-1">
                    <span>CONFIDENCE PROTOCOL</span>
                    <span
                      className={
                        result.final_verdict?.verdict === "FAKE"
                          ? "text-red-400"
                          : "text-green-400"
                      }
                    >
                      {result.final_verdict?.confidence_score || 0}% DETECTED
                    </span>
                  </div>
                  <div className="w-full bg-gray-800/50 rounded-full h-3 overflow-hidden border border-gray-600 relative">
                    <div className="absolute inset-0 z-10 w-full h-full flex justify-between px-1">
                      {[...Array(10)].map((_, i) => (
                        <div
                          key={i}
                          className="w-[1px] h-full bg-black/30"
                        ></div>
                      ))}
                    </div>
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{
                        width: `${
                          result.final_verdict?.confidence_score || 0
                        }%`,
                      }}
                      transition={{ duration: 1.5, ease: "circOut" }}
                      className={`h-full relative z-0 ${
                        result.final_verdict?.verdict === "FAKE"
                          ? "bg-gradient-to-r from-red-900 via-red-600 to-red-400"
                          : "bg-gradient-to-r from-green-900 via-green-600 to-green-400"
                      }`}
                    ></motion.div>
                  </div>
                </div>

                {/* SOURCES SECTION */}
                {result.final_verdict?.sources &&
                  result.final_verdict.sources.length > 0 && (
                    <div className="mt-6 border-t border-gray-700 pt-4 text-left">
                      <p className="text-xs text-gray-500 font-mono mb-2">
                        CORROBORATING SOURCES:
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {result.final_verdict.sources.map((source, i) => (
                          <a
                            key={i}
                            href={source.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="bg-gray-800 text-gray-300 text-xs px-2 py-1 rounded border border-gray-600 flex items-center gap-1 hover:bg-green-900 hover:text-green-400 hover:border-green-500 transition-all cursor-pointer"
                          >
                            🔗 {source.name}
                          </a>
                        ))}
                      </div>
                    </div>
                  )}
              </div>
            </div>

            {/* DETECTED CLAIM (If Auto-Detect was used) */}
            {result.auto_claim && !claim && (
              <div className="text-gray-400 text-xs text-center border border-gray-800 p-2 rounded bg-black/50 mx-auto w-full">
                <span className="text-green-500 font-bold">
                  [AUTO-DETECTED CONTEXT]:
                </span>{" "}
                {result.auto_claim}
              </div>
            )}

            <button
              onClick={() =>
                setResult(null) && setUrl("") && setClaim("") && setFile(null)
              }
              className="text-gray-500 hover:text-white underline text-center text-sm tracking-widest hover:tracking-[0.2em] transition-all pb-10"
            >
              [ RESET SYSTEM ]
            </button>
          </motion.div>
        )}
      </div>
    </div>
  );
}
