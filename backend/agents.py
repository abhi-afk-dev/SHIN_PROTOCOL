import os
import asyncio
import base64
import requests
import json
import re
import queue
import threading
import traceback
import time
import random
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.tools import DuckDuckGoSearchResults
from langchain_core.messages import HumanMessage
from duckduckgo_search import DDGS
import yt_dlp

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    YouTubeTranscriptApi = None

load_dotenv()

class ShinSwarm:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=os.getenv("GOOGLE_API_KEY"))

    def clean_json_output(self, text):
        default_verdict = {
            "verdict": "UNVERIFIED", 
            "confidence_score": 0, 
            "summary": "The system could not generate a conclusive verdict.", 
            "sources": []
        }

        try:
            data = None
            if isinstance(text, dict): 
                data = text
            else:
                text = text.replace("```json", "").replace("```", "")
                match = re.search(r'\{.*\}', text, re.DOTALL)
                if match: 
                    data = json.loads(match.group(0))
                else:
                    data = json.loads(text)
            
            if not data or "verdict" not in data:
                print("Warning: JSON missing keys, using default.")
                return default_verdict
                
            return data

        except Exception as e:
            print(f"JSON Clean Error: {e}")
            return default_verdict

    def _get_video_data(self, url):
        ydl_opts = {
            'quiet': True, 'noplaylist': True, 'skip_download': True,
            'extract_flat': True, 'no_warnings': True, 'ignoreerrors': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        }
        
        data = {"title": "Social Media Video", "description": "", "transcript": ""}
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    data['title'] = info.get('title', 'Social Media Video')
                    data['description'] = info.get('description', '') or info.get('caption', '')
        except:
            pass

        try:
            if YouTubeTranscriptApi and any(x in url for x in ['youtube', 'youtu.be', 'shorts']):
                video_id = None
                if "v=" in url: video_id = url.split("v=")[1].split("&")[0]
                elif "shorts" in url: video_id = url.split("shorts/")[1].split("?")[0]
                elif "youtu.be" in url: video_id = url.split("/")[-1].split("?")[0]
                
                if video_id:
                    t_list = YouTubeTranscriptApi.list_transcripts(video_id)
                    try: t = t_list.find_transcript(['en', 'en-US'])
                    except: t = t_list.find_generated_transcript(['en', 'en-US'])
                    data['transcript'] = " ".join([x['text'] for x in t.fetch()])[:2000]
        except:
            pass
            
        return data

    def _smart_search(self, query):
        print(f"DEBUG: Smart search for '{query}'")
        max_retries = 3
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }

        for attempt in range(max_retries):
            try:
                with DDGS(headers=headers) as ddgs:
                    results = []
                    
                    # STRATEGY 1: Try strict "News" search first
                    # If an event is real, this will have results.
                    try:
                        news_hits = list(ddgs.news(f"{query}", max_results=5))
                        if news_hits:
                            results.extend(news_hits)
                    except: pass

                    # STRATEGY 2: If News is empty, use "Text" search (Web)
                    if not results:
                        print("DEBUG: No news found, switching to General Web Search...")
                        web_hits = list(ddgs.text(f"{query} official status", max_results=5, backend='lite'))
                        results.extend(web_hits)

                    if results:
                        return json.dumps(results[:5])
                    
            except Exception as e:
                print(f"Search Attempt {attempt+1} failed: {e}")
                time.sleep(random.uniform(1, 2))
        
        return "SEARCH_UNAVAILABLE"

    async def run_search_agent(self, query, log_queue):
        await log_queue.put(json.dumps({"type": "log", "agent": "SEARCH", "message": f"Deep Scanning: {query}..."}))
        try:
            res = await asyncio.to_thread(self._smart_search, query)
            
            if res == "SEARCH_UNAVAILABLE":
                 await log_queue.put(json.dumps({"type": "log", "agent": "SEARCH", "message": "Search blocked. Using Logic Fallback."}))
            elif "[]" in res:
                 await log_queue.put(json.dumps({"type": "log", "agent": "SEARCH", "message": "No specific news found (Suggests Fake)."}))
            else:
                 await log_queue.put(json.dumps({"type": "log", "agent": "SEARCH", "message": "Intel Retrieved."}))
            
            return {"data": res} 
        except Exception as e:
            return {"data": "SEARCH_FAILED"}
        
    async def run_vision_agent(self, b64, claim, log_queue):
        await log_queue.put(json.dumps({"type": "log", "agent": "VISION", "message": "Analyzing visual data..."}))
        try:
            if not b64: return {"data": await self.llm.ainvoke(f"Check logic: {claim}").content}
            msg = HumanMessage(content=[
                {"type": "text", "text": "Describe for fact-checking:"},
                {"type": "image_url", "image_url": f"data:image/jpeg;base64,{b64}"}
            ])
            res = await self.llm.ainvoke([msg])
            return {"data": res.content}
        except: return {"data": "Vision Analysis Failed"}

    async def run_video_agent(self, url, claim, log_queue):
        await log_queue.put(json.dumps({"type": "log", "agent": "VIDEO_OPS", "message": "Extracting Metadata..."}))
        data = await asyncio.to_thread(self._get_video_data, url)
        
        context = f"Title: {data.get('title')}\nDesc: {data.get('description')}\nTranscript: {data.get('transcript')}"
        prompt = f"Analyze video context for truth: {context}. User Claim: {claim}"
        
        try:
            res = await self.llm.ainvoke(prompt)
            return {"data": res.content}
        except: return {"data": "Video Analysis Failed"}
            
    async def run_judge_agent(self, search, vision, claim, log_queue):
        await log_queue.put(json.dumps({"type": "log", "agent": "JUDGE", "message": "Finalizing Verdict..."}))
        prompt = f"""
        Act as Veritas Protocol Judge.
        User Claim: "{claim}"
        
        EVIDENCE PACK (Contains 2 Search Strategies): 
        {str(search)}
        
        VISUAL ANALYSIS: 
        {str(vision)[:1500]}
        
        CRITICAL INSTRUCTIONS:
        1. If "Fact Check" results are empty, look at "Latest News". And if the claim is AI-generated content, mark as Fake.
        2. CONTRADICTION CHECK: If the claim says someone "died today", but "Latest News" shows them attending events or active TODAY/YESTERDAY, the claim is FAKE.
        3. Ignore irrelevant results (e.g. historical articles from years ago).
        
        Return STRICT JSON: 
        {{ 
            "verdict": "REAL" | "FAKE", 
            "confidence_score": 0-100, 
            "summary": "Explain WHY based on the evidence found (e.g. 'Subject is active today according to news reports').", 
            "sources": [ {{"name": "News Outlet Name", "url": "https://..."}} ] 
        }}
        """
        try:
            res = await self.llm.ainvoke(prompt)
            return self.clean_json_output(res.content)
        except:
            return self.clean_json_output("{}")

    async def _investigate_internal(self, image_input, claim_text, is_file, log_queue):
        final_data = {"type": "result", "final_verdict": {"verdict": "ERROR", "confidence_score": 0, "summary": "System Error.", "sources": []}, "swarm_logs": [], "is_video": False, "auto_claim": claim_text}
        try:
            is_video = False
            if image_input and not is_file and any(x in image_input.lower() for x in ['youtube', 'youtu.be', 'instagram', 'tiktok']):
                is_video = True
            
            final_data['is_video'] = is_video
            
            # 1. IF VIDEO, EXTRACT DATA FIRST (BEFORE SEARCH)
            video_data = None
            if is_video:
                video_result = await self.run_video_agent(image_input, claim_text, log_queue)
                video_data = video_result['raw_metadata']
                video_context = video_result['data']

                # 2. AUTO-GENERATE CLAIM IF EMPTY
                if not claim_text or claim_text.strip() == "":
                    await log_queue.put(json.dumps({"type": "log", "agent": "SYSTEM", "message": "Auto-Detecting Claim from Video..."}))
                    
                    transcript_preview = video_data.get('transcript', '')[:1000]
                    desc_preview = video_data.get('description', '')[:500]
                    
                    # Ask LLM to extract the main claim
                    claim_prompt = f"""
                    Based on this video metadata, what is the Main Factual Claim being made?
                    Title: {video_data.get('title')}
                    Transcript: {transcript_preview}
                    Description: {desc_preview}
                    
                    Return ONLY the claim as a single sentence.
                    """
                    generated_claim = await self.llm.ainvoke(claim_prompt)
                    claim_text = generated_claim.content.strip()
                    final_data['auto_claim'] = claim_text # Send back to frontend
                    await log_queue.put(json.dumps({"type": "log", "agent": "SYSTEM", "message": f"Claim Detected: {claim_text}"}))
            
            else:
                # Image Logic
                video_context = ""
                if not is_file:
                    try: 
                        b64 = base64.b64encode(requests.get(image_input).content).decode('utf-8')
                        video_context = await self.run_vision_agent(b64, claim_text, log_queue)
                    except: pass

            # 3. NOW RUN SEARCH WITH THE (POSSIBLY AUTO-GENERATED) CLAIM
            search_task = self.run_search_agent(claim_text, log_queue)
            
            # Wait for search
            search_result = await search_task
            
            # 4. JUDGE
            verdict = await self.run_judge_agent(search_result, video_context, claim_text, log_queue)
            
            final_data['final_verdict'] = verdict
            final_data['swarm_logs'] = [search_result, {"data": "Visuals Processed"}]
            
        except Exception as e:
            await log_queue.put(json.dumps({"type": "log", "agent": "SYSTEM", "message": f"Error: {str(e)}"}))
        finally:
            await log_queue.put(json.dumps(final_data))
            await log_queue.put(None)
                  
    def investigate_stream_sync(self, image_input, claim_text, is_file=False):
        sync_q = queue.Queue()
        def start_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def wrapper():
                q = asyncio.Queue()
                asyncio.create_task(self._investigate_internal(image_input, claim_text, is_file, q))
                while True:
                    item = await q.get()
                    sync_q.put(item)
                    if item is None: break
            loop.run_until_complete(wrapper())
            loop.close()
            

        t = threading.Thread(target=start_loop)
        t.start()
        while True:
            item = sync_q.get()
            if item is None: break
            yield item + "\n"
        sync_q = queue.Queue()
        def start_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def wrapper():
                q = asyncio.Queue()
                asyncio.create_task(self._investigate_internal(image_input, claim_text, is_file, q))
                while True:
                    item = await q.get()
                    sync_q.put(item)
                    if item is None: break
            loop.run_until_complete(wrapper())
            loop.close()
            

        t = threading.Thread(target=start_loop)
        t.start()
        while True:
            item = sync_q.get()
            if item is None: break
            yield item + "\n"