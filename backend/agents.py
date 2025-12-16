import os
import asyncio
import base64
import requests
import json
import re
import queue
import threading
import time
import random
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from duckduckgo_search import DDGS
from langchain_core.messages import HumanMessage

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    YouTubeTranscriptApi = None

load_dotenv()

class ShinSwarm:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=os.getenv("GOOGLE_API_KEY"))

    def clean_json_output(self, text):
        default_verdict = {
            "verdict": "UNVERIFIED", 
            "confidence_score": 0, 
            "summary": "Analysis failed.", 
            "sources": []
        }
        try:
            text = text.replace("```json", "").replace("```", "")
            match = re.search(r'\{.*\}', text, re.DOTALL)
            data_str = match.group(0) if match else text
            data = json.loads(data_str)
            
            if "verdict" not in data: data["verdict"] = "UNVERIFIED"
            if "summary" not in data: data["summary"] = "No summary provided."
            if "sources" not in data: data["sources"] = []
            return data
        except Exception as e:
            return default_verdict

    def _get_video_data(self, url):
        data = {"title": "", "description": "", "transcript": ""}
        
        if "youtube" in url or "youtu.be" in url:
            try:
                oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
                res = requests.get(oembed_url, timeout=3)
                if res.status_code == 200:
                    js = res.json()
                    data['title'] = js.get('title', '')
                    data['description'] = f"Author: {js.get('author_name', 'Unknown')}"
            except: pass

        try:
            if YouTubeTranscriptApi and data['title']: 
                video_id = None
                if "v=" in url: video_id = url.split("v=")[1].split("&")[0]
                elif "shorts/" in url: video_id = url.split("shorts/")[1].split("?")[0]
                elif "youtu.be/" in url: video_id = url.split("youtu.be/")[1].split("?")[0]
                
                if video_id:
                    t_list = YouTubeTranscriptApi.list_transcripts(video_id)
                    try: t = t_list.find_transcript(['en', 'en-US'])
                    except: t = t_list.find_generated_transcript(['en', 'en-US'])
                    
                    data['transcript'] = " ".join([x['text'] for x in t.fetch()])[:2000]
        except: 
            pass
            
        return data

    def _smart_search(self, query):
        print(f"DEBUG: Search for '{query}'")
        max_retries = 2
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }

        for attempt in range(max_retries):
            try:
                with DDGS(headers=headers) as ddgs:
                    web_hits = list(ddgs.text(f"{query} fact check", max_results=5, backend='lite'))
                    if web_hits: return json.dumps(web_hits)
            except Exception as e:
                time.sleep(1)
        
        return "SEARCH_UNAVAILABLE"

    async def run_search_agent(self, query, log_queue):
        await log_queue.put(json.dumps({"type": "log", "agent": "SEARCH", "message": f"Scanning: {query}..."}))
        try:
            res = await asyncio.to_thread(self._smart_search, query)
            if res == "SEARCH_UNAVAILABLE":
                 await log_queue.put(json.dumps({"type": "log", "agent": "SEARCH", "message": "Search unavailable."}))
            elif "[]" in res:
                 await log_queue.put(json.dumps({"type": "log", "agent": "SEARCH", "message": "No direct results found."}))
            else:
                 await log_queue.put(json.dumps({"type": "log", "agent": "SEARCH", "message": "Intel Retrieved."}))
            return {"data": res} 
        except:
            return {"data": "SEARCH_FAILED"}
    
    async def run_vision_agent(self, b64, claim, log_queue):
        await log_queue.put(json.dumps({"type": "log", "agent": "VISION", "message": "Analyzing Visuals..."}))
        try:
            if not b64: return {"data": await self.llm.ainvoke(f"Check logic: {claim}").content}
            msg = HumanMessage(content=[
                {"type": "text", "text": "Describe this image for a fact-checker:"},
                {"type": "image_url", "image_url": f"data:image/jpeg;base64,{b64}"}
            ])
            res = await self.llm.ainvoke([msg])
            return {"data": res.content}
        except: return {"data": "Vision Analysis Failed"}

    async def run_video_agent(self, url, claim, log_queue):
        await log_queue.put(json.dumps({"type": "log", "agent": "VIDEO_OPS", "message": "Checking Video Metadata..."}))
        data = await asyncio.to_thread(self._get_video_data, url)
        
        return {
            "data": f"Title: {data.get('title')}\nDesc: {data.get('description')}\nTranscript: {data.get('transcript')}",
            "raw_metadata": data 
        }
            
    async def run_judge_agent(self, search, vision, claim, log_queue):
        await log_queue.put(json.dumps({"type": "log", "agent": "JUDGE", "message": "Final Verdict..."}))
        
        prompt = f"""
        Act as Veritas Protocol Judge.
        User Claim: "{claim}"
        
        SEARCH EVIDENCE: {str(search)}
        VISUAL/VIDEO EVIDENCE: {str(vision)[:2500]}
        
        INSTRUCTIONS:
        1. If the User Claim is just a URL (http...) and no other evidence exists, mark UNVERIFIED.
        2. If SEARCH EVIDENCE confirms the claim (or part of the video Title), mark REAL.
        3. If SEARCH EVIDENCE proves it false, mark FAKE.
        4. If evidence is missing, check logic: Is the claim plausible?
        
        Return STRICT JSON: 
        {{ 
            "verdict": "REAL" | "FAKE" | "UNVERIFIED", 
            "confidence_score": int, 
            "summary": "Brief explanation.", 
            "sources": [ {{"name": "Source Name", "url": "https://..."}} ] 
        }}
        """
        try:
            res = await self.llm.ainvoke(prompt)
            return self.clean_json_output(res.content)
        except Exception as e:
            return self.clean_json_output("{}")
    
    async def _investigate_internal(self, image_input, claim_text, is_file, log_queue):
        final_data = {"type": "result", "final_verdict": {"verdict": "ERROR", "confidence_score": 0, "summary": "System Error.", "sources": []}, "swarm_logs": [], "is_video": False, "auto_claim": claim_text}
        try:
            is_video = False
            if image_input and not is_file and any(x in image_input.lower() for x in ['youtube', 'youtu.be', 'instagram', 'tiktok']):
                is_video = True
            
            final_data['is_video'] = is_video
            
            video_context = ""
            if is_video:
                video_result = await self.run_video_agent(image_input, claim_text, log_queue)
                video_data = video_result.get('raw_metadata', {})
                video_context = video_result.get('data', "")
                
                if not claim_text or claim_text.strip() == "":
                    if video_data.get('title'):
                        claim_text = f"Check video claim: {video_data['title']}"
                        await log_queue.put(json.dumps({"type": "log", "agent": "SYSTEM", "message": f"Claim Found: {video_data['title']}"}))
                    else:
                        claim_text = f"Fact check this video: {image_input}"
                        await log_queue.put(json.dumps({"type": "log", "agent": "SYSTEM", "message": "Using Video URL as Claim"}))
                    
                    final_data['auto_claim'] = claim_text

            else:
                if not is_file:
                    try: 
                        b64 = base64.b64encode(requests.get(image_input).content).decode('utf-8')
                        video_context = await self.run_vision_agent(b64, claim_text, log_queue)
                    except: pass

            search_task = self.run_search_agent(claim_text, log_queue)
            search_result = await search_task
            
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
            try:
                item = sync_q.get(timeout=2.0)
                if item is None: break
                yield item + "\n"
            except queue.Empty:
                yield json.dumps({"type": "ping"}) + "\n"