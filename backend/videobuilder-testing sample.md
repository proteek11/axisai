--key "axisai_72_05wyTslb46owBbdTcKdQ_1A8_DZMhHzeKzUBPHME" \

curl -X POST http://localhost:8000/api/v1/video/jobs \
 -H "Authorization: Bearer axisai_72_05wyTslb46owBbdTcKdQ_1A8_DZMhHzeKzUBPHME" \
 -H "Content-Type: application/json" \
 -d '{
"job_id": 1,
"title": "Kinetic Test",
"video_type": "kinetic",
"script": "Learning is the engine of growth. Every concept mastered opens a new door.",
"language": "en",
"settings": {"duration_seconds": 15, "resolution": "720p"},
"callback_url": "https://httpbin.org/post"
}'

curl -s -X POST http://127.0.0.1:8000/api/v1/video/jobs \
 -H "Authorization: Bearer axisai_72_05wyTslb46owBbdTcKdQ_1A8_DZMhHzeKzUBPHME" \
 -H "Content-Type: application/json" \
 -H "X-Tenant-ID: 1" \
 -d '{
"job_id": 9,
"video_type": "kinetic",
"callback_url": "http://127.0.0.1/moodle/local/edzaxisvideo/callback.php",
"title": "Test Kinetic Video",
"script": "This is a test kinetic video about learning management systems.",
"duration": 30,
"style": "modern"
}' | python3 -m json.tool

{
"job_id": "ddb2ff74-17c3-40f0-93f3-826c86733051",
"moodle_job_id": 2,
"status": "queued",
"message": "Video job queued. Poll /api/v1/video/jobs/ddb2ff74-17c3-40f0-93f3-826c86733051 for status."
}

curl -s http://127.0.0.1:8000/api/v1/video/jobs/a92eb28b-f89a-48f9-a256-6965d5e77f02 \
 -H "Authorization: Bearer axisai_72_05wyTslb46owBbdTcKdQ_1A8_DZMhHzeKzUBPHME" \
 -H "X-Tenant-ID: 1" | python3 -m json.tool

Video output url - http://127.0.0.1:8000/video-outputs/1/f508a1af-18ca-4170-9963-911a9589766d/output.mp4

curl -s -X POST "http://127.0.0.1:8000/api/v1/video/jobs" \
 -H "Authorization: Bearer axisai_72_05wyTslb46owBbdTcKdQ_1A8_DZMhHzeKzUBPHME" \
 -H "Content-Type: application/json" \
 -d '{
"job_id": 1010,
"video_type": "slideshow",
"title": "Quick Safety Tips",
"language": "en",
"script": "Always wear your seatbelt. Keep your workspace clean and organized. Report any hazards immediately to your supervisor. Stay hydrated and take regular breaks during long shifts.",
"callback_url": "http://localhost/moodle/local/edzaxisvideo/callback.php",
"settings": {
"duration_seconds": 40,
"resolution": "720p",
"aspect_ratio": "9:16",
"transition": "fade",
"slidestyle": "minimal",
"slideperscene": 1,
"music_volume": 0.0,
"\_resolved_assets": {
"pdf_path": "/Users/EDZLEARN/Documents/Claude/Projects/moodle-axis-ai/test-assets/ailearning.pdf"
}
}
}' | python3 -m json.tool
