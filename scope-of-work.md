# Scope of Work (SOW)

## 1. Project Title

**CCTV People Detection, Gender Classification, Face Recognition, and Footfall Analysis**

## 2. Project Overview

This project analyzes recorded CCTV videos. It finds people in the video, follows their movement, saves images of them, estimates gender, and counts people who cross a selected line.

The project also includes a separately trained face-recognition feature. It uses CNN and KNN methods to recognize the project owner and selected friends. This feature is planned to be connected with the video analysis so that recognized people can be matched with the people seen in the video.

## 3. Objectives

- Find people in recorded CCTV videos.
- Follow each person as they move through the video.
- Save images of each tracked person for review.
- Remove poor-quality images and images that show only legs or too little of the body.
- Estimate whether a person is male or female using a trained model.
- Recognize the project owner and selected friends using the trained face-recognition feature.
- Count people crossing a selected line in the video.
- Create videos and images that show the results clearly.

## 4. Scope of Work

### Included work

1. **Video analysis**
   - Use recorded video files as input.
   - Read and process the video one frame at a time.
   - Show the video size, speed, and number of frames when processing starts.

2. **People detection and tracking**
   - Find people in each video frame.
   - Give each tracked person an ID.
   - Keep the same ID while the person remains visible.

3. **Image collection**
   - Save images of tracked people in separate folders.
   - Skip images that are too small or invalid.
   - Create contact sheets so the collected images can be reviewed quickly.

4. **Image filtering**
   - Select the clearest or largest image for each person.
   - Remove images with an unsuitable shape or size.
   - Remove images where the upper body cannot be seen clearly.

5. **Gender estimation**
   - Use a trained image model to estimate gender from selected person images.
   - Recheck a person at set points in the video.
   - Combine repeated results to reduce changes in the displayed label.

6. **Face recognition**
   - Use the separately trained CNN+KNN face-recognition feature.
   - Recognize the project owner and selected enrolled friends.
   - Connect recognized names with tracked people when a clear face is available.
   - Show the recognition result in the agreed output.

7. **Footfall counting**
   - Draw a horizontal line across the video.
   - Count a tracked person when they cross the line.
   - Record upward and downward crossings where required.

8. **Result videos and images**
   - Create videos with boxes around people, person IDs, labels, and counts.
   - Save selected video frames with detection boxes for review.
   - Print a summary after processing is complete.

## 5. Key Features / Functionalities

- Recorded-video processing.
- Person detection and tracking.
- Person IDs that remain consistent while people are visible.
- Automatic saving of person images.
- Contact sheets for reviewing collected images.
- Filtering of poor-quality and legs-only images.
- Gender estimation from selected images.
- Face recognition for the project owner and selected friends.
- Horizontal-line footfall counting.
- Annotated result videos.
- Adjustable detection confidence, video output path, model choice, and counting-line position.
- Progress messages and final result summaries.

Gender and face-recognition results are estimates from trained models. Their quality depends on the camera angle, lighting, image quality, and how clearly a person or face can be seen.

## 6. Deliverables

- A set of scripts for video analysis, person tracking, image collection, filtering, gender estimation, face recognition, and footfall counting.
- Trained person-detection models.
- The separately trained CNN+KNN face-recognition feature.
- Collected person images grouped by person ID.
- Filtered person images.
- Contact sheets for image review.
- Annotated output videos.
- Annotated still images from selected video frames.
- Footfall totals and gender summaries printed after processing.

## 7. Technologies Used

- Python.
- OpenCV for reading videos, handling images, and creating output videos.
- YOLOv8 for finding and tracking people.
- A Hugging Face image model for gender estimation.
- MediaPipe Pose for checking whether the upper body is visible.
- CNN and KNN methods for recognizing enrolled faces.
- Pillow and NumPy for image handling.

The exact software version used for the CNN and KNN face-recognition feature is not specified.

## 8. Project Timeline / Milestones

**To be determined.**

The project does not specify agreed dates or a fixed delivery schedule.

## 9. Out of Scope

- Live camera streaming.
- A website or mobile application.
- A database or online reporting dashboard.
- Cloud hosting or automatic online deployment.
- Employee attendance management.
- Recognition of people who have not been enrolled.
- Face recognition when the face is not visible or clear enough.
- Training a new gender or face-recognition model as part of this scope.
- Guaranteed accuracy in all lighting, camera angles, or crowded scenes.
- Automatic privacy, consent, or data-retention management.

## 10. Assumptions and Dependencies

- Input will be provided as a readable recorded video file.
- The required software and trained models will be available before the project is run.
- The face-recognition feature will have face examples for the project owner and each friend who should be recognized.
- Face recognition will only identify people who have been enrolled.
- A person must be visible long enough and clearly enough to be detected and tracked.
- A face must be large and clear enough for recognition to work.
- Results may change when people are far away, partly hidden, poorly lit, or facing away from the camera.
- The position of the counting line affects the footfall result.

## 11. Acceptance Criteria

The project will be accepted when:

1. A recorded video can be opened and processed successfully.
2. People can be detected and tracked with visible IDs.
3. Person images can be saved and reviewed in contact sheets.
4. Poor-quality and legs-only images can be separated from usable images.
5. Gender estimates can be produced for usable person images.
6. The face-recognition feature can recognize the project owner and enrolled friends in clear test images or video frames.
7. The video can show detection boxes, IDs, labels, and the counting line.
8. Footfall totals can be produced for people crossing the selected line.
9. An annotated output video and a processing summary can be produced.

Recognition and gender estimation will be judged using clear test images and enrolled people. The project does not promise perfect results in poor lighting, crowded scenes, unclear images, or situations where a face is hidden.