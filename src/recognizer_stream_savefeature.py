import sys
sys.path.append('../insightface/deploy')
sys.path.append('../insightface/src/common')

from keras.models import load_model
from mtcnn.mtcnn import MTCNN
from imutils import paths
import face_preprocess
import numpy as np
import face_model
import argparse
import pickle
import time
import dlib
import cv2
import os

ap = argparse.ArgumentParser()

ap.add_argument("--mymodel", default="outputs/my_model.h5",
    help="Path to recognizer model")
ap.add_argument("--le", default="outputs/le.pickle",
    help="Path to label encoder")
ap.add_argument("--embeddings", default="outputs/embeddings.pickle",
    help='Path to embeddings')
ap.add_argument("--video-out", default="../datasets/videos_output/stream_test.mp4",
    help='Path to output video')


ap.add_argument('--image-size', default='112,112', help='')
ap.add_argument('--model', default='../insightface/models/model-y1-test2/model,0', help='path to load model.')
ap.add_argument('--ga-model', default='', help='path to load model.')
ap.add_argument('--gpu', default=0, type=int, help='gpu id')
ap.add_argument('--det', default=0, type=int, help='mtcnn option, 1 means using R+O, 0 means detect from begining')
ap.add_argument('--flip', default=0, type=int, help='whether do lr flip aug')
ap.add_argument('--threshold', default=1.24, type=float, help='ver dist threshold')

args = ap.parse_args()

# Load embeddings and labels
data = pickle.loads(open(args.embeddings, "rb").read())
#le = pickle.loads(open(args.le, "rb").read())	#200625

embeddings = np.array(data['embeddings'])
print("first:{}".format(np.shape(embeddings)))
labels = np.array(data['names'])        	#200625
#labels = le.fit_transform(data['names'])	
#labels = le.transform(data['names'])	        #200625

indexNumber = 0
#labels = np.array(data['names'])

# Initialize detector
detector = MTCNN()

# Initialize faces embedding model
embedding_model =face_model.FaceModel(args)

# Load the classifier model
model = load_model('outputs/my_model.h5')

#200626 임시,미완성
#def classify(vector1, vector2)
#    vec1 = vector1.flatten()
#    vec2 = vec2.flatten()
#    return False
# Define distance function
def findCosineDistance(vector1, vector2):
    """
    Calculate cosine distance between two vector
    """
    vec1 = vector1.flatten()
    vec2 = vector2.flatten()
    #print("vec1={}".format(np.shape(vec1)))

    a = np.dot(vec1, vec2)    #200626   a = np.dot(vec1.T, vec2)
    b = np.dot(vec1.T, vec1)
    c = np.dot(vec2.T, vec2)
    return 1 - (a/(np.sqrt(b)*np.sqrt(c)))

def CosineSimilarity(test_vec, source_vecs):
    """
    Verify the similarity of one vector to group vectors of one class
    """
    cos_dist = 0
    curr = 0
    minimum = 10
    temp = -1
    index = 0
    for source_vec in source_vecs:
        #cos_dist += findCosineDistance(test_vec, source_vec)
        curr = findCosineDistance(test_vec, source_vec)
        if curr < minimum :
            temp = index
            minimum = curr
        cos_dist += curr
        index += 1
    return cos_dist/len(source_vecs), temp

# Initialize some useful arguments
cosine_threshold = 0.97
proba_threshold = 0.85
comparing_num = 5
trackers = []
texts = []
frames = 0

# Start streaming and recording
cap = cv2.VideoCapture(0)
frame_width = int(cap.get(3))
frame_height = int(cap.get(4))
save_width = 600
save_height = int(600/frame_width*frame_height)
# video_out = cv2.VideoWriter(args.video_out, cv2.VideoWriter_fourcc('M','J','P','G'), 30, (save_width,save_height))

previous_embedding = []
new_labels = []
new_embeddings = []
while True:
    ret, frame = cap.read()
    frames += 1
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    frame = cv2.resize(frame, (save_width, save_height))

    if True:#frames%7 == 0:
        trackers = []
        texts = []

        detect_tick = time.time()
        bboxes = detector.detect_faces(frame)
        detect_tock = time.time()

        if len(bboxes) != 0:
            reco_tick = time.time()
            for bboxe in bboxes:
                bbox = bboxe['box']
                bbox = np.array([bbox[0], bbox[1], bbox[0]+bbox[2], bbox[1]+bbox[3]])
                landmarks = bboxe['keypoints']
                landmarks = np.array([landmarks["left_eye"][0], landmarks["right_eye"][0], landmarks["nose"][0], landmarks["mouth_left"][0], landmarks["mouth_right"][0],
                                     landmarks["left_eye"][1], landmarks["right_eye"][1], landmarks["nose"][1], landmarks["mouth_left"][1], landmarks["mouth_right"][1]])
                landmarks = landmarks.reshape((2,5)).T
                nimg = face_preprocess.preprocess(frame, bbox, landmarks, image_size='112,112')
                nimg = cv2.cvtColor(nimg, cv2.COLOR_BGR2RGB)
                nimg = np.transpose(nimg, (2,0,1))
                embedding = embedding_model.get_feature(nimg).reshape(1,-1)

                text = "Unknown"
	
                ### Predict class
                preds = model.predict(embedding)
                preds = preds.flatten()

                ## Get the highest accuracy embedded vector
                #j = np.argmax(preds)
                #proba = preds[j]

                ## Compare this vector to source class vectors to verify it is actual belong to this class
                #match_class_idx = (labels == j)
                #match_class_idx = np.where(match_class_idx)[0]
                #selected_idx = np.random.choice(match_class_idx, comparing_num)
                #compare_embeddings = embeddings[selected_idx]

                # Calculate cosine similarity
                cos_similarity, j = CosineSimilarity(embedding, embeddings)
                print("Sim:{:.2f}, index:{}".format(cos_similarity,j))

                if previous_embedding == []:
                    previous_cos_similarity = cosine_threshold
                    print("!!!first")
                else:
                    previous_cos_similarity, _ = CosineSimilarity(embedding, previous_embedding)
                if cos_similarity < cosine_threshold: #and proba > proba_threshold:
                    print("I know you and your name")                   
                    #name = le.classes_[j]#200625
                    name = labels[j]
                    print("name : {}".format(name))
                    #name = labels[j]
                    text = "{}".format(name)
                    #print("Recognized: {} <{:.2f}>".format(name, proba*100))
                else:
                    print("I don't know you")
                    if previous_cos_similarity >= cosine_threshold:
                        print("Unknown_new_face")
                        text = "Person" + str(indexNumber)
                        #new_embeddings.append(embedding)
                        #new_labels.append(text + str(indexNumber))
                        embeddings=np.concatenate((embeddings, embedding))
                        labels=np.append(labels, text)
                        indexNumber += 1
                        previous_embedding.append(embedding)
                        new_labels.append(text)
                        new_embeddings.append(embedding)

# todo  new_embedding 파일로 저장 + new_labels 저장 -> 하나로.pickle


                # Start tracking
                tracker = dlib.correlation_tracker()
                rect = dlib.rectangle(bbox[0], bbox[1], bbox[2], bbox[3])
                tracker.start_track(rgb, rect)
                trackers.append(tracker)
                texts.append(text)

                y = bbox[1] - 10 if bbox[1] - 10 > 10 else bbox[1] + 10
                cv2.putText(frame, text, (bbox[0], y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 2)
                cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (255,0,0), 2)
    else:
        for tracker, text in zip(trackers,texts):
            pos = tracker.get_position()

            # unpack the position object
            startX = int(pos.left())
            startY = int(pos.top())
            endX = int(pos.right())
            endY = int(pos.bottom())

            cv2.rectangle(frame, (startX, startY), (endX, endY), (255,0,0), 2)
            cv2.putText(frame, text, (startX, startY - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,0,255),2)

    cv2.imshow("Frame", frame)
    # video_out.write(frame)
    # print("Faces detection time: {}s".format(detect_tock-detect_tick))
    # print("Faces recognition time: {}s".format(reco_tock-reco_tick))
    key = cv2.waitKey(1) & 0xFF

    if key == ord("q"):
        break

# video_out.release()
cap.release()
#save to output
print(np.shape(embeddings))
new_data = {"embeddings": embeddings, "names": labels}
f = open(args.embeddings, "wb")
f.write(pickle.dumps(new_data))
f.close()
cv2.destroyAllWindows()
