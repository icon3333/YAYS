# Quick Add Video Feature - Implementation Plan

**Overall Progress:** `100%` (8/8 tasks completed)

---

## Overview

Add functionality to manually add individual YouTube videos to the feed via URL input, following the same design pattern as "Add Channel" in the Channels tab.

---

## Tasks:

- [x] 🟩 **Step 1: Database Schema Update**
  - [x] 🟩 Add `source_type` column to videos table (TEXT, default 'via_channel')
  - [x] 🟩 Create migration logic to add column to existing databases
  - [x] 🟩 Update VideoDatabase.add_video() to accept source_type parameter
  - [x] 🟩 Update all SELECT queries to include source_type field
  - [x] 🟩 Add index on source_type for query performance
  - [x] 🟩 Remove deprecated cleanup_old_videos() method

- [x] 🟩 **Step 2: Backend API Endpoint**
  - [x] 🟩 Create SingleVideoAdd Pydantic model with URL validation
  - [x] 🟩 Implement extract_video_id_from_url() helper function
  - [x] 🟩 Create POST /api/videos/add-single endpoint
  - [x] 🟩 Extract video ID from URL (support youtube.com, youtu.be, video ID)
  - [x] 🟩 Validate duplicate videos (return 400 if already processed)
  - [x] 🟩 Fetch video metadata using ytdlp_client
  - [x] 🟩 Validate video is not a short (respect SKIP_SHORTS setting)
  - [x] 🟩 Insert video to database with source_type='via_manual'
  - [x] 🟩 Trigger background processing via subprocess
  - [x] 🟩 Return success response with video details

- [x] 🟩 **Step 3: Frontend UI - Feed Tab**
  - [x] 🟩 Add "Quick Add Video" section at top of Feed tab
  - [x] 🟩 Create input field for YouTube video URL
  - [x] 🟩 Add "Process Video" button
  - [x] 🟩 Add status message container for feedback
  - [x] 🟩 Use consistent styling with "Add Channel" design

- [x] 🟩 **Step 4: Frontend JavaScript Logic**
  - [x] 🟩 Implement addSingleVideo() async function
  - [x] 🟩 Validate URL input before API call
  - [x] 🟩 Show loading state on button during processing
  - [x] 🟩 Call /api/videos/add-single endpoint
  - [x] 🟩 Handle success response (show message, clear input, reload feed)
  - [x] 🟩 Handle error responses (show error message)
  - [x] 🟩 Implement showSingleVideoStatus() helper function
  - [x] 🟩 Add Enter key support for quick submission

- [x] 🟩 **Step 5: Visual Differentiation**
  - [x] 🟩 Update feed rendering logic to check source_type
  - [x] 🟩 Add "• Manual" badge next to channel name for via_manual videos
  - [x] 🟩 Create .manual-badge CSS class with subtle italic styling
  - [x] 🟩 Ensure badge appears between channel name and date

- [x] 🟩 **Step 6: Integration & Processing Flow**
  - [x] 🟩 Ensure manual videos use existing transcript extraction
  - [x] 🟩 Ensure manual videos use existing AI summarization
  - [x] 🟩 Ensure manual videos respect SEND_EMAIL_SUMMARIES setting
  - [x] 🟩 Ensure manual videos appear in feed with correct status
  - [x] 🟩 Ensure feed auto-refreshes during processing
  - [x] 🟩 Verify manual videos follow same cleanup rules (MAX_PROCESSED_ENTRIES)

- [x] 🟩 **Step 7: Error Handling & Validation**
  - [x] 🟩 Handle invalid YouTube URLs (return clear error)
  - [x] 🟩 Handle duplicate videos (return "already processed" error)
  - [x] 🟩 Handle YouTube Shorts when SKIP_SHORTS=true
  - [x] 🟩 Handle missing video metadata (video not found/inaccessible)
  - [x] 🟩 Handle transcript extraction failures (same as channel videos)
  - [x] 🟩 Handle network errors on frontend

- [x] 🟩 **Step 8: Testing & Commit**
  - [x] 🟩 Verify database migration works on existing databases
  - [x] 🟩 Test URL extraction for all supported formats
  - [x] 🟩 Test duplicate detection
  - [x] 🟩 Test shorts filtering
  - [x] 🟩 Test complete flow: URL → processing → summary → feed display
  - [x] 🟩 Test "• Manual" badge appears correctly
  - [x] 🟩 Commit all changes with descriptive message
  - [x] 🟩 Push to feature branch

---

## Design Decisions

### Cleanup Behavior
- **Option B Selected**: Manual videos follow same MAX_PROCESSED_ENTRIES cleanup as channel videos

### Visual Style
- **Option 1 Selected**: Badge next to channel name (`Tech Channel • Manual`)

### UI State
- **Always Visible**: Section always visible for consistency with Channels tab

### URL Formats Supported
- `https://youtube.com/watch?v=VIDEO_ID`
- `https://youtu.be/VIDEO_ID`
- `VIDEO_ID` (11 characters)
- YouTube Shorts URLs (rejected if SKIP_SHORTS=true)

### Processing Behavior
- **Background processing**: Same as channel videos
- **No blocking**: UI remains responsive during processing
- **Auto-refresh**: Feed updates every 5 seconds while videos are processing

---

## Files Modified

1. **src/managers/database.py** - Database schema and migration
2. **src/web/app.py** - Backend API endpoint
3. **src/templates/index.html** - UI section in Feed tab
4. **src/static/js/app.js** - JavaScript logic
5. **src/static/css/main.css** - Badge styling

---

## Success Criteria

- ✅ User can paste YouTube URL in Feed tab
- ✅ Click "Process Video" to add video manually
- ✅ Video appears in feed with "Processing..." status
- ✅ Video is processed with transcript + AI summary + email
- ✅ Manual videos show "• Manual" badge in feed
- ✅ Duplicate videos are rejected with clear error
- ✅ Shorts are rejected if SKIP_SHORTS=true
- ✅ Invalid URLs show helpful error messages
- ✅ All processing uses centralized pipeline
- ✅ Manual videos respect cleanup rules
