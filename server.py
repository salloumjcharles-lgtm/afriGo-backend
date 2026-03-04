1|from fastapi import FastAPI, APIRouter, HTTPException, Depends, status
2|from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
3|from dotenv import load_dotenv
4|from starlette.middleware.cors import CORSMiddleware
5|from motor.motor_asyncio import AsyncIOMotorClient
6|import os
7|import logging
8|from pathlib import Path
9|from pydantic import BaseModel, Field
10|from typing import List, Optional
11|import uuid
12|from datetime import datetime, timedelta
13|from passlib.context import CryptContext
14|from jose import JWTError, jwt
15|
16|ROOT_DIR = Path(__file__).parent
17|load_dotenv(ROOT_DIR / '.env')
18|
19|# MongoDB connection
20|mongo_url = os.environ['MONGO_URL']
21|client = AsyncIOMotorClient(mongo_url)
22|db = client[os.environ.get('DB_NAME', 'afrigo_db')]
23|
24|# JWT Settings
25|SECRET_KEY = os.environ.get('SECRET_KEY', 'afrigo-secret-key-2025-ivory-coast')
26|ALGORITHM = "HS256"
27|ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days
28|
29|# Password hashing
30|pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
31|security = HTTPBearer()
32|
33|# Create the main app
34|app = FastAPI(title="AfriGo - VTC Côte d'Ivoire")
35|
36|# Create a router with the /api prefix
37|api_router = APIRouter(prefix="/api")
38|
39|# ==================== MODELS ====================
40|
41|class UserBase(BaseModel):
42|    phone: str
43|    full_name: str
44|    email: Optional[str] = None
45|
46|class UserRegister(UserBase):
47|    password: str
48|    user_type: str = "client"  # "client" or "driver"
49|
50|class UserLogin(BaseModel):
51|    phone: str
52|    password: str
53|
54|class User(UserBase):
55|    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
56|    user_type: str
57|    created_at: datetime = Field(default_factory=datetime.utcnow)
58|    is_active: bool = True
59|    profile_complete: bool = False
60|
61|class Token(BaseModel):
62|    access_token: str
63|    token_type: str
64|    user: dict
65|
66|class DriverInfo(BaseModel):
67|    user_id: str
68|    vehicle_type: str  # "moto", "voiture", "taxi"
69|    vehicle_brand: str
70|    vehicle_model: str
71|    vehicle_color: str
72|    plate_number: str
73|    license_number: Optional[str] = None
74|    is_available: bool = False
75|    current_location: Optional[dict] = None  # {"lat": float, "lng": float}
76|    rating: float = 5.0
77|    total_rides: int = 0
78|
79|class DriverInfoCreate(BaseModel):
80|    vehicle_type: str
81|    vehicle_brand: str
82|    vehicle_model: str
83|    vehicle_color: str
84|    plate_number: str
85|    license_number: Optional[str] = None
86|
87|class RideRequest(BaseModel):
88|    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
89|    client_id: str
90|    client_name: str
91|    client_phone: str
92|    pickup_address: str
93|    pickup_location: dict  # {"lat": float, "lng": float}
94|    destination_address: str
95|    destination_location: dict
96|    vehicle_type: str
97|    payment_method: str  # "cash", "orange_money", "wave"
98|    status: str = "pending"  # pending, accepted, in_progress, completed, cancelled
99|    driver_id: Optional[str] = None
100|    driver_name: Optional[str] = None
101|    driver_phone: Optional[str] = None
102|    estimated_price: float = 0
103|    final_price: Optional[float] = None
104|    created_at: datetime = Field(default_factory=datetime.utcnow)
105|    accepted_at: Optional[datetime] = None
106|    completed_at: Optional[datetime] = None
107|
108|class RideRequestCreate(BaseModel):
109|    pickup_address: str
110|    pickup_location: dict
111|    destination_address: str
112|    destination_location: dict
113|    vehicle_type: str
114|    payment_method: str
115|
116|# ==================== AUTH HELPERS ====================
117|
118|def verify_password(plain_password: str, hashed_password: str) -> bool:
119|    return pwd_context.verify(plain_password, hashed_password)
120|
121|def get_password_hash(password: str) -> str:
122|    return pwd_context.hash(password)
123|
124|def create_access_token(data: dict) -> str:
125|    to_encode = data.copy()
126|    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
127|    to_encode.update({"exp": expire})
128|    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
129|    return encoded_jwt
130|
131|async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
132|    credentials_exception = HTTPException(
133|        status_code=status.HTTP_401_UNAUTHORIZED,
134|        detail="Identifiants invalides",
135|        headers={"WWW-Authenticate": "Bearer"},
136|    )
137|    try:
138|        token = credentials.credentials
139|        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
140|        user_id: str = payload.get("sub")
141|        if user_id is None:
142|            raise credentials_exception
143|    except JWTError:
144|        raise credentials_exception
145|    
146|    user = await db.users.find_one({"id": user_id})
147|    if user is None:
148|        raise credentials_exception
149|    return user
150|
151|# ==================== PRICE CALCULATION ====================
152|
153|def calculate_ride_price(pickup: dict, destination: dict, vehicle_type: str) -> float:
154|    """Calculate estimated price based on distance and vehicle type"""
155|    import math
156|    
157|    # Calculate distance using Haversine formula
158|    lat1, lon1 = pickup.get("lat", 0), pickup.get("lng", 0)
159|    lat2, lon2 = destination.get("lat", 0), destination.get("lng", 0)
160|    
161|    R = 6371  # Earth's radius in km
162|    dlat = math.radians(lat2 - lat1)
163|    dlon = math.radians(lon2 - lon1)
164|    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
165|    c = 2 * math.asin(math.sqrt(a))
166|    distance = R * c
167|    
168|    # Base prices per km in CFA
169|    price_per_km = {
170|        "moto": 200,
171|        "voiture": 350,
172|        "taxi": 300
173|    }
174|    
175|    base_price = {
176|        "moto": 500,
177|        "voiture": 1000,
178|        "taxi": 800
179|    }
180|    
181|    price = base_price.get(vehicle_type, 500) + (distance * price_per_km.get(vehicle_type, 250))
182|    
183|    # Round to nearest 100 CFA
184|    return round(price / 100) * 100
185|
186|# ==================== AUTH ROUTES ====================
187|
188|@api_router.post("/auth/register", response_model=Token)
189|async def register(user_data: UserRegister):
190|    # Check if phone already exists
191|    existing_user = await db.users.find_one({"phone": user_data.phone})
192|    if existing_user:
193|        raise HTTPException(
194|            status_code=status.HTTP_400_BAD_REQUEST,
195|            detail="Ce numéro de téléphone est déjà enregistré"
196|        )
197|    
198|    # Create user
199|    user = User(
200|        phone=user_data.phone,
201|        full_name=user_data.full_name,
202|        email=user_data.email,
203|        user_type=user_data.user_type
204|    )
205|    
206|    user_dict = user.dict()
207|    user_dict["hashed_password"] = get_password_hash(user_data.password)
208|    
209|    await db.users.insert_one(user_dict)
210|    
211|    # Create token
212|    access_token = create_access_token(data={"sub": user.id})
213|    
214|    return {
215|        "access_token": access_token,
216|        "token_type": "bearer",
217|        "user": {
218|            "id": user.id,
219|            "phone": user.phone,
220|            "full_name": user.full_name,
221|            "user_type": user.user_type,
222|            "profile_complete": user.profile_complete
223|        }
224|    }
225|
226|@api_router.post("/auth/login", response_model=Token)
227|async def login(login_data: UserLogin):
228|    user = await db.users.find_one({"phone": login_data.phone})
229|    if not user:
230|        raise HTTPException(
231|            status_code=status.HTTP_401_UNAUTHORIZED,
232|            detail="Numéro de téléphone ou mot de passe incorrect"
233|        )
234|    
235|    if not verify_password(login_data.password, user.get("hashed_password", "")):
236|        raise HTTPException(
237|            status_code=status.HTTP_401_UNAUTHORIZED,
238|            detail="Numéro de téléphone ou mot de passe incorrect"
239|        )
240|    
241|    access_token = create_access_token(data={"sub": user["id"]})
242|    
243|    # Get driver info if user is a driver
244|    driver_info = None
245|    if user.get("user_type") == "driver":
246|        driver_info = await db.drivers.find_one({"user_id": user["id"]}, {"_id": 0})
247|    
248|    return {
249|        "access_token": access_token,
250|        "token_type": "bearer",
251|        "user": {
252|            "id": user["id"],
253|            "phone": user["phone"],
254|            "full_name": user["full_name"],
255|            "user_type": user["user_type"],
256|            "profile_complete": user.get("profile_complete", False),
257|            "driver_info": driver_info
258|        }
259|    }
260|
261|@api_router.get("/auth/me")
262|async def get_me(current_user: dict = Depends(get_current_user)):
263|    driver_info = None
264|    if current_user.get("user_type") == "driver":
265|        driver_info = await db.drivers.find_one({"user_id": current_user["id"]}, {"_id": 0})
266|    
267|    return {
268|        "id": current_user["id"],
269|        "phone": current_user["phone"],
270|        "full_name": current_user["full_name"],
271|        "email": current_user.get("email"),
272|        "user_type": current_user["user_type"],
273|        "profile_complete": current_user.get("profile_complete", False),
274|        "driver_info": driver_info
275|    }
276|
277|# ==================== DRIVER ROUTES ====================
278|
279|@api_router.post("/driver/register-vehicle")
280|async def register_driver_vehicle(
281|    driver_data: DriverInfoCreate,
282|    current_user: dict = Depends(get_current_user)
283|):
284|    if current_user.get("user_type") != "driver":
285|        raise HTTPException(
286|            status_code=status.HTTP_403_FORBIDDEN,
287|            detail="Seuls les chauffeurs peuvent enregistrer un véhicule"
288|        )
289|    
290|    # Check if driver already has vehicle registered
291|    existing = await db.drivers.find_one({"user_id": current_user["id"]})
292|    if existing:
293|        # Update existing
294|        await db.drivers.update_one(
295|            {"user_id": current_user["id"]},
296|            {"$set": driver_data.dict()}
297|        )
298|    else:
299|        # Create new
300|        driver_info = DriverInfo(
301|            user_id=current_user["id"],
302|            **driver_data.dict()
303|        )
304|        await db.drivers.insert_one(driver_info.dict())
305|    
306|    # Update user profile_complete
307|    await db.users.update_one(
308|        {"id": current_user["id"]},
309|        {"$set": {"profile_complete": True}}
310|    )
311|    
312|    return {"message": "Véhicule enregistré avec succès"}
313|
314|@api_router.put("/driver/availability")
315|async def update_driver_availability(
316|    is_available: bool,
317|    current_user: dict = Depends(get_current_user)
318|):
319|    if current_user.get("user_type") != "driver":
320|        raise HTTPException(status_code=403, detail="Accès non autorisé")
321|    
322|    await db.drivers.update_one(
323|        {"user_id": current_user["id"]},
324|        {"$set": {"is_available": is_available}}
325|    )
326|    
327|    return {"message": "Disponibilité mise à jour", "is_available": is_available}
328|
329|@api_router.put("/driver/location")
330|async def update_driver_location(
331|    location: dict,
332|    current_user: dict = Depends(get_current_user)
333|):
334|    if current_user.get("user_type") != "driver":
335|        raise HTTPException(status_code=403, detail="Accès non autorisé")
336|    
337|    await db.drivers.update_one(
338|        {"user_id": current_user["id"]},
339|        {"$set": {"current_location": location}}
340|    )
341|    
342|    return {"message": "Position mise à jour"}
343|
344|@api_router.get("/driver/rides")
345|async def get_driver_rides(
346|    status_filter: Optional[str] = None,
347|    current_user: dict = Depends(get_current_user)
348|):
349|    if current_user.get("user_type") != "driver":
350|        raise HTTPException(status_code=403, detail="Accès non autorisé")
351|    
352|    query = {"driver_id": current_user["id"]}
353|    if status_filter:
354|        query["status"] = status_filter
355|    
356|    rides = await db.rides.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
357|    return rides
358|
359|@api_router.get("/driver/pending-rides")
360|async def get_pending_rides(current_user: dict = Depends(get_current_user)):
361|    if current_user.get("user_type") != "driver":
362|        raise HTTPException(status_code=403, detail="Accès non autorisé")
363|    
364|    # Get driver info
365|    driver = await db.drivers.find_one({"user_id": current_user["id"]}, {"_id": 0})
366|    if not driver:
367|        raise HTTPException(status_code=400, detail="Profil chauffeur incomplet")
368|    
369|    # Get pending rides matching driver's vehicle type
370|    rides = await db.rides.find({
371|        "status": "pending",
372|        "vehicle_type": driver["vehicle_type"]
373|    }, {"_id": 0}).sort("created_at", -1).to_list(50)
374|    
375|    return rides
376|
377|# ==================== RIDE ROUTES ====================
378|
379|@api_router.post("/rides/request")
380|async def create_ride_request(
381|    ride_data: RideRequestCreate,
382|    current_user: dict = Depends(get_current_user)
383|):
384|    if current_user.get("user_type") != "client":
385|        raise HTTPException(status_code=403, detail="Seuls les clients peuvent demander une course")
386|    
387|    # Calculate estimated price
388|    estimated_price = calculate_ride_price(
389|        ride_data.pickup_location,
390|        ride_data.destination_location,
391|        ride_data.vehicle_type
392|    )
393|    
394|    ride = RideRequest(
395|        client_id=current_user["id"],
396|        client_name=current_user["full_name"],
397|        client_phone=current_user["phone"],
398|        pickup_address=ride_data.pickup_address,
399|        pickup_location=ride_data.pickup_location,
400|        destination_address=ride_data.destination_address,
401|        destination_location=ride_data.destination_location,
402|        vehicle_type=ride_data.vehicle_type,
403|        payment_method=ride_data.payment_method,
404|        estimated_price=estimated_price
405|    )
406|    
407|    await db.rides.insert_one(ride.dict())
408|    
409|    return ride.dict()
410|
411|@api_router.put("/rides/{ride_id}/accept")
412|async def accept_ride(
413|    ride_id: str,
414|    current_user: dict = Depends(get_current_user)
415|):
416|    if current_user.get("user_type") != "driver":
417|        raise HTTPException(status_code=403, detail="Accès non autorisé")
418|    
419|    ride = await db.rides.find_one({"id": ride_id})
420|    if not ride:
421|        raise HTTPException(status_code=404, detail="Course non trouvée")
422|    
423|    if ride["status"] != "pending":
424|        raise HTTPException(status_code=400, detail="Cette course n'est plus disponible")
425|    
426|    # Update ride with driver info
427|    await db.rides.update_one(
428|        {"id": ride_id},
429|        {
430|            "$set": {
431|                "status": "accepted",
432|                "driver_id": current_user["id"],
433|                "driver_name": current_user["full_name"],
434|                "driver_phone": current_user["phone"],
435|                "accepted_at": datetime.utcnow()
436|            }
437|        }
438|    )
439|    
440|    # Update driver availability
441|    await db.drivers.update_one(
442|        {"user_id": current_user["id"]},
443|        {"$set": {"is_available": False}}
444|    )
445|    
446|    return {"message": "Course acceptée"}
447|
448|@api_router.put("/rides/{ride_id}/start")
449|async def start_ride(
450|    ride_id: str,
451|    current_user: dict = Depends(get_current_user)
452|):
453|    ride = await db.rides.find_one({"id": ride_id})
454|    if not ride:
455|        raise HTTPException(status_code=404, detail="Course non trouvée")
456|    
457|    if ride["driver_id"] != current_user["id"]:
458|        raise HTTPException(status_code=403, detail="Accès non autorisé")
459|    
460|    await db.rides.update_one(
461|        {"id": ride_id},
462|        {"$set": {"status": "in_progress"}}
463|    )
464|    
465|    return {"message": "Course démarrée"}
466|
467|@api_router.put("/rides/{ride_id}/complete")
468|async def complete_ride(
469|    ride_id: str,
470|    current_user: dict = Depends(get_current_user)
471|):
472|    ride = await db.rides.find_one({"id": ride_id})
473|    if not ride:
474|        raise HTTPException(status_code=404, detail="Course non trouvée")
475|    
476|    if ride["driver_id"] != current_user["id"]:
477|        raise HTTPException(status_code=403, detail="Accès non autorisé")
478|    
479|    await db.rides.update_one(
480|        {"id": ride_id},
481|        {
482|            "$set": {
483|                "status": "completed",
484|                "final_price": ride["estimated_price"],
485|                "completed_at": datetime.utcnow()
486|            }
487|        }
488|    )
489|    
490|    # Update driver stats
491|    await db.drivers.update_one(
492|        {"user_id": current_user["id"]},
493|        {
494|            "$set": {"is_available": True},
495|            "$inc": {"total_rides": 1}
496|        }
497|    )
498|    
499|    return {"message": "Course terminée"}
500|
501|@api_router.put("/rides/{ride_id}/cancel")
502|async def cancel_ride(
503|    ride_id: str,
504|    current_user: dict = Depends(get_current_user)
505|):
506|    ride = await db.rides.find_one({"id": ride_id})
507|    if not ride:
508|        raise HTTPException(status_code=404, detail="Course non trouvée")
509|    
510|    # Check if user is authorized to cancel
511|    if ride["client_id"] != current_user["id"] and ride.get("driver_id") != current_user["id"]:
512|        raise HTTPException(status_code=403, detail="Accès non autorisé")
513|    
514|    if ride["status"] in ["completed", "cancelled"]:
515|        raise HTTPException(status_code=400, detail="Impossible d'annuler cette course")
516|    
517|    await db.rides.update_one(
518|        {"id": ride_id},
519|        {"$set": {"status": "cancelled"}}
520|    )
521|    
522|    # If driver had accepted, make them available again
523|    if ride.get("driver_id"):
524|        await db.drivers.update_one(
525|            {"user_id": ride["driver_id"]},
526|            {"$set": {"is_available": True}}
527|        )
528|    
529|    return {"message": "Course annulée"}
530|
531|@api_router.get("/rides/my-rides")
532|async def get_my_rides(
533|    status_filter: Optional[str] = None,
534|    current_user: dict = Depends(get_current_user)
535|):
536|    if current_user.get("user_type") == "client":
537|        query = {"client_id": current_user["id"]}
538|    else:
539|        query = {"driver_id": current_user["id"]}
540|    
541|    if status_filter:
542|        query["status"] = status_filter
543|    
544|    rides = await db.rides.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
545|    return rides
546|
547|@api_router.get("/rides/{ride_id}")
548|async def get_ride(
549|    ride_id: str,
550|    current_user: dict = Depends(get_current_user)
551|):
552|    ride = await db.rides.find_one({"id": ride_id}, {"_id": 0})
553|    if not ride:
554|        raise HTTPException(status_code=404, detail="Course non trouvée")
555|    
556|    # Check authorization
557|    if ride["client_id"] != current_user["id"] and ride.get("driver_id") != current_user["id"]:
558|        raise HTTPException(status_code=403, detail="Accès non autorisé")
559|    
560|    return ride
561|
562|@api_router.get("/rides/active")
563|async def get_active_ride(current_user: dict = Depends(get_current_user)):
564|    if current_user.get("user_type") == "client":
565|        ride = await db.rides.find_one({
566|            "client_id": current_user["id"],
567|            "status": {"$in": ["pending", "accepted", "in_progress"]}
568|        }, {"_id": 0})
569|    else:
570|        ride = await db.rides.find_one({
571|            "driver_id": current_user["id"],
572|            "status": {"$in": ["accepted", "in_progress"]}
573|        }, {"_id": 0})
574|    
575|    return ride
576|
577|# ==================== HEALTH CHECK ====================
578|
579|@api_router.get("/")
580|async def root():
581|    return {"message": "AfriGo API - VTC Côte d'Ivoire", "status": "ok"}
582|
583|@api_router.get("/health")
584|async def health():
585|    return {"status": "healthy", "service": "AfriGo API"}
586|
587|# Include the router in the main app
588|app.include_router(api_router)
589|
590|app.add_middleware(
591|    CORSMiddleware,
592|    allow_credentials=True,
593|    allow_origins=["*"],
594|    allow_methods=["*"],
595|    allow_headers=["*"],
596|)
597|
598|# Configure logging
599|logging.basicConfig(
600|    level=logging.INFO,
601|    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
602|)
603|logger = logging.getLogger(__name__)
604|
605|@app.on_event("shutdown")
606|async def shutdown_db_client():
607|    client.close()
608|
[End of file]
