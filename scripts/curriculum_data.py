"""
Course catalog for SOT, PDEU — transcribed from the official B.Tech course-structure
documents (data/photos/<branch>/).

Course code scheme follows the printed convention seen in the Mechanical and Chemical
documents: 24<AREA><YEAR><NN><T|P>
    24    - curriculum revision year (w.e.f. 2024-25)
    AREA  - 2-letter subject area (MA/PH/CH/BT/CV/CP/EE/HS/ME/CS/IT/EC)
    YEAR  - 1..4, first digit of the 3-digit number
    NN    - sequence within that year
    T|P   - Theory / Practical (lab) component
Non-conforming codes that appear verbatim in the documents are kept as printed
(24INT151, 24PRME452, 24YOG101, 24NSS101, 24NCC101, MOOC).

Only the Mechanical and Chemical documents printed course codes. Codes for CS, ICT,
ECE and Civil subjects are generated to the same convention (their code column was
blank in the source documents).

SUBJECTS: subject_code -> (name, category, L, T, P, credits)
    category: BSC Basic Science / ESC Engineering Science / HSC Humanities & Social
    Science / PC Program Core / PE Program Elective / OE Open Elective / PRO Project

CURRICULUM: dept_code -> semester -> [subject_code, ...]
"""

# ---------------------------------------------------------------------------
# Shared first-year basket (semesters 1-2, common across branches with variations)
# ---------------------------------------------------------------------------
SHARED = {
    "24MA101T": ("Mathematics - I", "BSC", 3, 1, 0, 4),
    "24MA102T": ("Mathematics for Biotechnology - I", "BSC", 3, 1, 0, 4),
    "24MA103T": ("Mathematics - II", "BSC", 3, 1, 0, 4),
    "24MA104T": ("Mathematics for Biotechnology - II", "BSC", 3, 1, 0, 4),
    "24PH101T": ("Applied Physics", "BSC", 3, 0, 0, 3),
    "24PH101P": ("Applied Physics Laboratory", "BSC", 0, 0, 2, 1),
    "24PH102T": ("Engineering Physics", "BSC", 3, 0, 0, 3),
    "24PH102P": ("Engineering Physics Laboratory", "BSC", 0, 0, 2, 1),
    "24PH103T": ("Modern Physics", "BSC", 3, 0, 0, 3),
    "24PH103P": ("Modern Physics Laboratory", "BSC", 0, 0, 2, 1),
    "24CH101T": ("Engineering Chemistry", "BSC", 3, 0, 0, 3),
    "24CH101P": ("Engineering Chemistry Laboratory", "BSC", 0, 0, 2, 1),
    "24BT101T": ("Biological Systems for Engineers", "BSC", 2, 0, 0, 2),
    "24BT102T": ("Biology for Engineers", "BSC", 2, 0, 0, 2),
    "24CV101T": ("Environmental Science", "BSC", 2, 0, 0, 2),
    "24CP101T": ("Computer Programming - I", "ESC", 1, 0, 0, 1),
    "24CP101P": ("Computer Programming - I Laboratory", "ESC", 0, 0, 2, 1),
    "24CP102T": ("Computer Programming - II", "ESC", 1, 0, 0, 1),
    "24CP102P": ("Computer Programming - II Laboratory", "ESC", 0, 0, 2, 1),
    "24EE101T": ("Elements of Electrical and Electronics Engineering", "ESC", 3, 0, 0, 3),
    "24EE101P": ("Elements of Electrical and Electronics Engineering Laboratory", "ESC", 0, 0, 2, 1),
    "24ME101P": ("Workshop Practices", "ESC", 0, 0, 2, 1),
    "24ME102P": ("Engineering Graphics", "ESC", 0, 0, 4, 2),
    "24HS101T": ("English Communication", "HSC", 2, 0, 0, 2),
    "24HS102T": ("Universal Human Values", "HSC", 1, 0, 0, 1),
    "24HS103T": ("Indian Knowledge System", "HSC", 2, 0, 0, 2),
    "24HS104T": ("Organizational Behaviour", "HSC", 1, 0, 0, 1),
    "24HS105T": ("Professional Communication", "HSC", 2, 0, 0, 2),
    "24YOG101": ("Yoga, Health & Hygiene", "HSC", 0, 0, 2, 1),
    "24NSS101": ("National Service Scheme (NSS)", "HSC", 0, 0, 2, 1),
    "24NCC101": ("National Cadet Corps (NCC)", "HSC", 0, 0, 2, 1),
    # shared later-year service courses
    "24MA201T": ("Mathematics - III", "BSC", 3, 1, 0, 4),
    "24MA202T": ("Discrete Mathematics", "BSC", 3, 1, 0, 4),
    "24HS301T": ("Engineering Economics", "HSC", 3, 0, 0, 3),
    "24INT151": ("Civic and Social Service Internship", "PRO", 0, 0, 0, 1),
    "24INT251": ("Industrial Orientation", "PRO", 0, 0, 0, 0),
    "24INT451": ("Summer Internship", "PRO", 0, 0, 0, 2),
    "MOOC": ("NPTEL / SWAYAM / MOOC Course", "OE", 3, 0, 0, 3),
    "24OE201T": ("Open Elective 1 (From Other School)", "OE", 3, 0, 0, 3),
    "24OE301T": ("Open Elective 3 (From Other Department of FoET)", "OE", 3, 0, 0, 3),
    "24OE401T": ("Open Elective 4 (From Other Department of FoET)", "OE", 3, 0, 0, 3),
}

# ---------------------------------------------------------------------------
# Computer Science (dept CP, area CS)
# ---------------------------------------------------------------------------
CS = {
    "24CS201T": ("Database Management System", "PC", 3, 0, 0, 3),
    "24CS201P": ("Database Management System Laboratory", "PC", 0, 0, 2, 1),
    "24CS202T": ("Digital Logic and Design", "PC", 3, 1, 0, 4),
    "24CS203T": ("Data Structures", "PC", 3, 0, 0, 3),
    "24CS203P": ("Data Structures Laboratory", "PC", 0, 0, 2, 1),
    "24CS204T": ("Object Oriented Programming", "PC", 3, 0, 0, 3),
    "24CS204P": ("Object Oriented Programming Laboratory", "PC", 0, 0, 2, 1),
    "24CS205P": ("Design Thinking", "PC", 0, 0, 2, 1),
    "24CS206T": ("Probability and Statistics Theory", "PC", 3, 0, 0, 3),
    "24CS207T": ("Computer Organization and Architecture", "PC", 3, 1, 0, 4),
    "24CS208T": ("Software Engineering", "PC", 3, 0, 0, 3),
    "24CS208P": ("Software Engineering Laboratory", "PC", 0, 0, 2, 1),
    "24CS209T": ("Theory of Computation", "PC", 3, 1, 0, 4),
    "24CS210T": ("Design and Analysis of Algorithm", "PC", 3, 0, 0, 3),
    "24CS210P": ("Design and Analysis of Algorithm Laboratory", "PC", 0, 0, 2, 1),
    "24CS301T": ("Introduction to Artificial Intelligence", "ESC", 3, 0, 0, 3),
    "24CS302T": ("Computer Networks", "PC", 3, 0, 0, 3),
    "24CS302P": ("Computer Networks Laboratory", "PC", 0, 0, 2, 1),
    "24CS303T": ("Compiler Design", "PC", 3, 0, 0, 3),
    "24CS303P": ("Compiler Design Laboratory", "PC", 0, 0, 2, 1),
    "24CS304T": ("Operating System", "PC", 3, 0, 0, 3),
    "24CS304P": ("Operating System Laboratory", "PC", 0, 0, 2, 1),
    "24CS305T": ("Cryptography and Network Security", "PC", 3, 0, 0, 3),
    "24CS305P": ("Cryptography and Network Security Laboratory", "PC", 0, 0, 2, 1),
    "24CS306T": ("Web & Mobile Development Essentials", "PC", 1, 0, 0, 1),
    "24CS306P": ("Web & Mobile Development Essentials Laboratory", "PC", 0, 0, 4, 2),
    "24CS307T": ("Distributed Computing", "PC", 3, 0, 0, 3),
    "24CS307P": ("Distributed Computing Laboratory", "PC", 0, 0, 2, 1),
    "24CS401T": ("Industry 4.0", "ESC", 2, 0, 0, 2),
    "24CS401P": ("Industry 4.0 Laboratory", "ESC", 0, 0, 2, 1),
    "24CS402T": ("Machine Learning", "PC", 3, 0, 0, 3),
    "24CS402P": ("Machine Learning Laboratory", "PC", 0, 0, 2, 1),
    "24CS403T": ("Cyber Laws and Ethics", "PC", 1, 0, 0, 1),
    "24PRCS451": ("Seminar", "PRO", 0, 0, 0, 1),
    "24PRCS452": ("Major/Comprehensive Project", "PRO", 0, 0, 0, 12),
    # Track-based program electives (List of Electives screenshot)
    "24CS331T": ("Data Mining and Data Warehousing", "PE", 3, 0, 0, 3),
    "24CS332T": ("Object Oriented Modelling and Design", "PE", 3, 0, 0, 3),
    "24CS333T": ("Computer Graphics", "PE", 3, 0, 0, 3),
    "24CS334T": ("Advanced Data Structure and Algorithms", "PE", 3, 0, 0, 3),
    "24CS335T": ("Data Communication", "PE", 3, 0, 0, 3),
    "24CS336T": ("Soft Computing", "PE", 3, 0, 0, 3),
    "24CS337T": ("UI/UX Design", "PE", 3, 0, 0, 3),
    "24CS338T": ("Digital Image Processing", "PE", 3, 0, 0, 3),
    "24CS339T": ("Blockchain Technology", "PE", 3, 0, 0, 3),
    "24CS340T": ("Mobile Computing", "PE", 3, 0, 0, 3),
    "24CS341T": ("Deep Learning", "PE", 3, 0, 0, 3),
    "24CS342T": ("Secure Software Engineering", "PE", 3, 0, 0, 3),
    "24CS343T": ("Computer Vision", "PE", 3, 0, 0, 3),
    "24CS344T": ("Big Data Analytics", "PE", 3, 0, 0, 3),
    "24CS345T": ("Wireless Sensor Networks", "PE", 3, 0, 0, 3),
    "24CS431T": ("Agent based Learning", "PE", 3, 0, 0, 3),
    "24CS432T": ("Agile and DevOps", "PE", 3, 0, 0, 3),
    "24CS433T": ("Natural Language Processing", "PE", 3, 0, 0, 3),
    "24CS434T": ("Cloud Computing", "PE", 3, 0, 0, 3),
    "24CS435T": ("Internet of Things", "PE", 3, 0, 0, 3),
    "24CS436T": ("Machine Learning in Cyber Security", "PE", 3, 0, 0, 3),
    "24CS437T": ("Web Application Testing", "PE", 3, 0, 0, 3),
    "24CS438T": ("Speech Processing", "PE", 3, 0, 0, 3),
    "24CS439T": ("Quantum Computing", "PE", 3, 0, 0, 3),
    "24CS440T": ("Autonomous Systems", "PE", 3, 0, 0, 3),
}

# ---------------------------------------------------------------------------
# Information & Communication Technology (dept IT, area IT)
# ---------------------------------------------------------------------------
ICT = {
    "24IT201T": ("Introduction to Artificial Intelligence", "ESC", 3, 0, 0, 3),
    "24IT202T": ("Digital Circuits", "PC", 3, 0, 0, 3),
    "24IT202P": ("Digital Circuits Laboratory", "PC", 0, 0, 2, 1),
    "24IT203T": ("Data Structures and Algorithms", "PC", 3, 0, 0, 3),
    "24IT203P": ("Data Structures and Algorithms Laboratory", "PC", 0, 0, 2, 1),
    "24IT204T": ("Fundamentals of ICT", "PC", 2, 0, 0, 2),
    "24IT205T": ("Electronics Devices and Circuits", "PC", 2, 0, 0, 2),
    "24IT206T": ("Industry 4.0", "ESC", 2, 0, 0, 2),
    "24IT206P": ("Industry 4.0 Laboratory", "ESC", 0, 0, 2, 1),
    "24IT207T": ("Database Management Systems", "PC", 3, 0, 0, 3),
    "24IT207P": ("Database Management Systems Laboratory", "PC", 0, 0, 2, 1),
    "24IT208T": ("Principles of Programming Languages", "PC", 3, 0, 0, 3),
    "24IT208P": ("Principles of Programming Languages Laboratory", "PC", 0, 0, 2, 1),
    "24IT209T": ("Fundamentals of Signal Processing & Communication", "PC", 3, 1, 0, 4),
    "24IT210T": ("Computer Organization & Microprocessor", "PC", 3, 0, 0, 3),
    "24IT210P": ("Computer Organization & Microprocessor Laboratory", "PC", 0, 0, 2, 1),
    "24IT301T": ("Theory of Computation & Compiler Design", "PC", 3, 0, 0, 3),
    "24IT301P": ("Theory of Computation & Compiler Design Laboratory", "PC", 0, 0, 2, 1),
    "24IT302T": ("Digital Signal Processing", "PC", 3, 0, 0, 3),
    "24IT302P": ("Digital Signal Processing Laboratory", "PC", 0, 0, 2, 1),
    "24IT303T": ("RF Engineering", "PC", 3, 0, 0, 3),
    "24IT303P": ("RF Engineering Laboratory", "PC", 0, 0, 2, 1),
    "24IT304T": ("Operating Systems", "PC", 3, 0, 0, 3),
    "24IT304P": ("Operating Systems Laboratory", "PC", 0, 0, 2, 1),
    "24IT305T": ("Digital Communication", "PC", 3, 0, 0, 3),
    "24IT305P": ("Digital Communication Laboratory", "PC", 0, 0, 2, 1),
    "24IT306T": ("Computer Communication and Networking", "PC", 3, 0, 0, 3),
    "24IT306P": ("Computer Communication and Networking Laboratory", "PC", 0, 0, 2, 1),
    "24IT401T": ("Software Engineering Methodology", "PC", 3, 0, 0, 3),
    "24IT401P": ("Software Engineering Methodology Laboratory", "PC", 0, 0, 2, 1),
    "24IT402T": ("Embedded Systems", "PC", 3, 0, 0, 3),
    "24IT402P": ("Embedded Systems Laboratory", "PC", 0, 0, 2, 1),
    "24IT403T": ("Digital CMOS and VLSI Design", "PC", 3, 0, 0, 3),
    "24IT403P": ("Digital CMOS and VLSI Design Laboratory", "PC", 0, 0, 2, 1),
    "24PRIT451": ("Seminar", "PRO", 0, 0, 0, 1),
    "24PRIT452": ("Major/Comprehensive Project", "PRO", 0, 0, 0, 12),
    # Program core electives (Program Core Electives screenshot)
    "24IT331T": ("Web Technology", "PE", 3, 0, 0, 3),
    "24IT332T": ("Problem Solving through Java", "PE", 3, 0, 0, 3),
    "24IT333T": ("Optimization Methods and Algorithms", "PE", 3, 0, 0, 3),
    "24IT334T": ("Introduction to CMOS and Memory Technology", "PE", 3, 0, 0, 3),
    "24IT335T": ("Cloud Architecture and Service", "PE", 3, 0, 0, 3),
    "24IT336T": ("Advanced Web Technology", "PE", 3, 0, 0, 3),
    "24IT337T": ("Advanced Algorithm Design", "PE", 3, 0, 0, 3),
    "24IT338T": ("Machine Learning", "PE", 3, 0, 0, 3),
    "24IT339T": ("Data Warehousing & Mining", "PE", 3, 0, 0, 3),
    "24IT340T": ("Image Processing", "PE", 3, 0, 0, 3),
    "24IT341T": ("Statistical Signal Processing", "PE", 3, 0, 0, 3),
    "24IT342T": ("Hardware Accelerated Computing", "PE", 3, 0, 0, 3),
    "24IT431T": ("Cryptography and Network Security", "PE", 3, 0, 0, 3),
    "24IT432T": ("Internet of Things", "PE", 3, 0, 0, 3),
    "24IT433T": ("Blockchain Technology", "PE", 3, 0, 0, 3),
    "24IT434T": ("Mobile Application Development", "PE", 3, 0, 0, 3),
    "24IT435T": ("Computer Vision", "PE", 3, 0, 0, 3),
    "24IT436T": ("Deep Learning and Reinforcement Learning", "PE", 3, 0, 0, 3),
    "24IT437T": ("Optical Communication", "PE", 3, 0, 0, 3),
    "24IT438T": ("Modern Wireless Communications", "PE", 3, 0, 0, 3),
    "24IT439T": ("Autonomous Systems", "PE", 3, 0, 0, 3),
    "24IT440T": ("Real Time Operating Systems", "PE", 3, 0, 0, 3),
}

# ---------------------------------------------------------------------------
# Electronics & Communication (dept EC, area EC)
# ---------------------------------------------------------------------------
ECE = {
    "24EC201T": ("Introduction to Artificial Intelligence", "ESC", 3, 0, 0, 3),
    "24EC202T": ("Digital Circuits", "PC", 3, 0, 0, 3),
    "24EC202P": ("Digital Circuits Laboratory", "PC", 0, 0, 2, 1),
    "24EC203T": ("Electronics Devices and Circuits", "PC", 3, 0, 0, 3),
    "24EC203P": ("Electronics Devices and Circuits Laboratory", "PC", 0, 0, 2, 1),
    "24EC204T": ("Networks and Systems", "PC", 3, 1, 0, 4),
    "24EC205T": ("Industry 4.0", "ESC", 2, 0, 0, 2),
    "24EC205P": ("Industry 4.0 Laboratory", "ESC", 0, 0, 2, 1),
    "24EC206T": ("Analog Electronics", "PC", 3, 0, 0, 3),
    "24EC206P": ("Analog Electronics Laboratory", "PC", 0, 0, 2, 1),
    "24EC207T": ("Analog Communication", "PC", 3, 0, 0, 3),
    "24EC207P": ("Analog Communication Laboratory", "PC", 0, 0, 2, 1),
    "24EC208T": ("Electromagnetics and Transmission Lines", "PC", 3, 1, 0, 4),
    "24EC209T": ("Digital Signal Processing", "PC", 3, 0, 0, 3),
    "24EC209P": ("Digital Signal Processing Laboratory", "PC", 0, 0, 2, 1),
    "24EC301T": ("Control Systems", "PC", 3, 0, 0, 3),
    "24EC301P": ("Control Systems Lab", "PC", 0, 0, 2, 1),
    "24EC302T": ("Linear Integrated Circuits and Applications", "PC", 3, 0, 0, 3),
    "24EC302P": ("Linear Integrated Circuits and Applications Laboratory", "PC", 0, 0, 2, 1),
    "24EC303T": ("Digital Communication", "PC", 3, 0, 0, 3),
    "24EC303P": ("Digital Communication Laboratory", "PC", 0, 0, 2, 1),
    "24EC304T": ("Computer and Communication Networks", "PC", 3, 0, 0, 3),
    "24EC304P": ("Computer and Communication Networks Laboratory", "PC", 0, 0, 2, 1),
    "24EC305T": ("Computer Organization and Microprocessor", "PC", 3, 0, 0, 3),
    "24EC305P": ("Computer Organization and Microprocessor Lab", "PC", 0, 0, 2, 1),
    "24EC306T": ("Microwave and Antenna", "PC", 3, 0, 0, 3),
    "24EC306P": ("Microwave and Antenna Lab", "PC", 0, 0, 2, 1),
    "24EC401T": ("Modern Wireless Communication", "PC", 3, 0, 0, 3),
    "24EC401P": ("Modern Wireless Communication Lab", "PC", 0, 0, 2, 1),
    "24EC402T": ("Embedded System Design", "PC", 3, 0, 0, 3),
    "24EC402P": ("Embedded System Design Lab", "PC", 0, 0, 2, 1),
    "24EC403T": ("Digital CMOS VLSI Design", "PC", 3, 0, 0, 3),
    "24EC403P": ("Digital CMOS VLSI Design Lab", "PC", 0, 0, 2, 1),
    "24PREC451": ("Seminar", "PRO", 0, 0, 0, 1),
    "24PREC452": ("Major/Comprehensive Project", "PRO", 0, 0, 0, 12),
    # Program core electives (Program Core Electives screenshot)
    "24EC331T": ("Digital Systems Design using HDL", "PE", 3, 0, 0, 3),
    "24EC332T": ("Opto Electronics and Optical Communication", "PE", 3, 0, 0, 3),
    "24EC333T": ("Analog IC Design", "PE", 3, 0, 0, 3),
    "24EC334T": ("Power Electronics", "PE", 3, 0, 0, 3),
    "24EC335T": ("Satellite Communication", "PE", 3, 0, 0, 3),
    "24EC336T": ("Information Theory and Coding", "PE", 3, 0, 0, 3),
    "24EC337T": ("Machine Learning and Applications", "PE", 3, 0, 0, 3),
    "24EC338T": ("Database Management Systems", "PE", 3, 0, 0, 3),
    "24EC339T": ("Introduction to Robotics", "PE", 3, 0, 0, 3),
    "24EC340T": ("Modern Control Systems", "PE", 3, 0, 0, 3),
    "24EC431T": ("Advanced Processors and SoCs", "PE", 3, 0, 0, 3),
    "24EC432T": ("IC Technology", "PE", 3, 0, 0, 3),
    "24EC433T": ("Mixed Signal VLSI Design", "PE", 3, 0, 0, 3),
    "24EC434T": ("Advanced Communication Networks", "PE", 3, 0, 0, 3),
    "24EC435T": ("Radar and Navigation Systems", "PE", 3, 0, 0, 3),
    "24EC436T": ("Internet of Things", "PE", 3, 0, 0, 3),
    "24EC437T": ("Deep Learning and Applications", "PE", 3, 0, 0, 3),
    "24EC438T": ("Drones: Design, Theory and Applications", "PE", 3, 0, 0, 3),
}

# ---------------------------------------------------------------------------
# Mechanical (dept ME, area ME) — codes printed verbatim in source documents
# ---------------------------------------------------------------------------
MECH = {
    "24ME201T": ("Introduction to Artificial Intelligence", "PC", 3, 0, 0, 3),
    "24ME202T": ("Engineering Mechanics", "PC", 3, 0, 0, 3),
    "24ME203T": ("Thermodynamics", "PC", 3, 0, 0, 3),
    "24ME203P": ("Thermodynamics Laboratory", "PC", 0, 0, 2, 1),
    "24ME204T": ("Mechanical Measurement and Metrology", "PC", 3, 0, 0, 3),
    "24ME204P": ("Mechanical Measurement and Metrology Laboratory", "PC", 0, 0, 2, 1),
    "24ME205P": ("Mechanical Drawing Laboratory", "PC", 0, 0, 2, 1),
    "24ME205T": ("Industry 4.0", "ESC", 2, 0, 0, 2),
    "24ME206T": ("Fluid Mechanics", "PC", 3, 0, 0, 3),
    "24ME206P": ("Fluid Mechanics Laboratory", "PC", 0, 0, 2, 1),
    "24ME207T": ("Design and Kinematics of Machines", "PC", 3, 0, 0, 3),
    "24ME207P": ("Design and Kinematics of Machines Laboratory", "PC", 0, 0, 2, 1),
    "24ME208T": ("Engineering Metallurgy", "PC", 3, 0, 0, 3),
    "24ME208P": ("Engineering Metallurgy Laboratory", "PC", 0, 0, 2, 1),
    "24ME209T": ("Strength of Material", "PC", 3, 0, 0, 3),
    "24ME209P": ("Strength of Material Laboratory", "PC", 0, 0, 2, 1),
    "24ME221T": ("Renewable Energy", "OE", 3, 0, 0, 3),
    "24ME301T": ("Heat Transfer", "PC", 3, 0, 0, 3),
    "24ME301P": ("Heat Transfer Laboratory", "PC", 0, 0, 2, 1),
    "24ME302T": ("Dynamics of Machine", "PC", 3, 0, 0, 3),
    "24ME302P": ("Dynamics of Machine Laboratory", "PC", 0, 0, 2, 1),
    "24ME303T": ("Manufacturing Processes - I", "PC", 3, 0, 0, 3),
    "24ME303P": ("Manufacturing Processes - I Laboratory", "PC", 0, 0, 2, 1),
    "24ME304T": ("Refrigeration and Air Conditioning", "PC", 3, 0, 0, 3),
    "24ME304P": ("Refrigeration and Air Conditioning Laboratory", "PC", 0, 0, 2, 1),
    "24ME305T": ("Machine Design - I", "PC", 3, 0, 0, 3),
    "24ME305P": ("Machine Design - I Laboratory", "PC", 0, 0, 2, 1),
    "24ME306T": ("Manufacturing Processes - II", "PC", 3, 0, 0, 3),
    "24ME306P": ("Manufacturing Processes - II Laboratory", "PC", 0, 0, 2, 1),
    "24ME307T": ("Robotics", "PC", 3, 0, 0, 3),
    "24ME307P": ("Robotics Laboratory", "PC", 0, 0, 2, 1),
    "24ME401T": ("Optimization Techniques", "PC", 3, 0, 0, 3),
    "24ME402T": ("Project Management", "PC", 3, 0, 0, 3),
    "24ME403P": ("Computational Engineering Laboratory", "PC", 0, 0, 4, 2),
    "24PRME451": ("Seminar", "PRO", 0, 0, 0, 1),
    "24PRME452": ("Major Project", "PRO", 0, 0, 0, 12),
    "24PRME453": ("Comprehensive Project", "PRO", 0, 0, 0, 12),
    "24ME331T": ("Introduction to Composite Materials", "PE", 3, 0, 0, 3),
    "24ME332T": ("Renewable and Sustainable Energy Technologies", "PE", 3, 0, 0, 3),
    "24ME333T": ("Fluid Machinery", "PE", 3, 0, 0, 3),
    "24ME334T": ("Laser and Electron Beam Material Processing", "PE", 3, 0, 0, 3),
    "24ME335T": ("Mechanical Vibration", "PE", 3, 0, 0, 3),
    "24ME336T": ("Additive Manufacturing", "PE", 3, 0, 0, 3),
    "24ME337T": ("Production and Operation Management", "PE", 3, 0, 0, 3),
    "24ME338T": ("Heat Exchanger Design", "PE", 3, 0, 0, 3),
    "24ME431T": ("Exergy Analysis of Thermal Systems", "PE", 3, 0, 0, 3),
    "24ME432T": ("Machine Design - II", "PE", 3, 0, 0, 3),
    "24ME433T": ("Micro and Nano Manufacturing", "PE", 3, 0, 0, 3),
    "24ME434T": ("Cryogenics", "PE", 3, 0, 0, 3),
    "24ME435T": ("CAD", "PE", 3, 0, 0, 3),
    "24ME436T": ("Welding for Metal Joining, Surfacing and Additive Manufacturing", "PE", 3, 0, 0, 3),
    "24ME437T": ("Automobile Engineering", "PE", 3, 0, 0, 3),
    "24ME438T": ("Computer Aided Manufacturing", "PE", 3, 0, 0, 3),
    "24ME439T": ("Non-Destructive Testing and Failure Analysis", "PE", 3, 0, 0, 3),
    "24ME440T": ("Material and Procurement Management", "PE", 3, 0, 0, 3),
}

# ---------------------------------------------------------------------------
# Civil (dept CE, area CV)
# ---------------------------------------------------------------------------
CIVIL = {
    "24CV201T": ("Introduction to Artificial Intelligence", "ESC", 3, 0, 0, 3),
    "24CV202T": ("Building Materials and Construction Technology", "PC", 3, 0, 0, 3),
    "24CV203T": ("Building Planning and Computer Aided Drawing", "PC", 1, 0, 2, 2),
    "24CV204T": ("Solid Mechanics", "PC", 4, 0, 0, 4),
    "24CV205T": ("Concrete Technology", "PC", 2, 0, 0, 2),
    "24CV206P": ("Material Testing Laboratory", "PC", 0, 0, 2, 1),
    "24CV207T": ("Industry 4.0", "ESC", 2, 0, 0, 2),
    "24CV207P": ("Industry 4.0 Laboratory", "ESC", 0, 0, 2, 1),
    "24CV208T": ("Fluid Mechanics", "PC", 3, 0, 2, 4),
    "24CV209T": ("Engineering Geology and Soil Mechanics", "PC", 3, 0, 2, 4),
    "24CV210T": ("Surveying Practices", "PC", 3, 0, 2, 4),
    "24CV211T": ("Structural Analysis", "PC", 3, 1, 0, 4),
    "24CV301T": ("Hydrology and Water Resources", "PC", 3, 0, 2, 4),
    "24CV302T": ("Foundation and Geotechnical Applications", "PC", 3, 0, 2, 4),
    "24CV303T": ("Design of RCC Structures", "PC", 3, 0, 0, 3),
    "24CV304P": ("Computer Aided Design Drawing Lab - I", "PC", 0, 0, 2, 1),
    "24CV305T": ("Design of Steel Structures", "PC", 3, 0, 0, 3),
    "24CV306P": ("Computer Aided Design Drawing Lab - II", "PC", 0, 0, 2, 1),
    "24CV307T": ("Environmental Engineering", "PC", 3, 0, 2, 4),
    "24CV308T": ("Highway and Traffic Engineering", "PC", 3, 0, 2, 4),
    "24CV401T": ("Estimation Costing Contracts and Valuations", "PC", 3, 1, 0, 4),
    "24CV402T": ("Project Management", "PC", 3, 0, 2, 4),
    "24CV403T": ("Earthquake Engineering", "PC", 3, 1, 0, 4),
    "24PRCV451": ("Seminar", "PRO", 0, 0, 0, 1),
    "24PRCV452": ("Major/Comprehensive Project", "PRO", 0, 0, 0, 12),
    # The Civil source document lists PE slots without naming the electives.
    # Placeholder rows keep the slot structure faithful to the document.
    "24CV331T": ("Program Elective 1", "PE", 3, 0, 0, 3),
    "24CV332T": ("Program Elective 2", "PE", 3, 0, 0, 3),
    "24CV333T": ("Program Elective 3", "PE", 3, 0, 0, 3),
    "24CV431T": ("Program Elective 4", "PE", 3, 0, 0, 3),
    "24CV432T": ("Program Elective 5", "PE", 3, 0, 0, 3),
}

# ---------------------------------------------------------------------------
# Chemical (dept CH, area CH — 1xx numbers are the shared chemistry service
# courses, 2xx and above are Chemical Engineering program courses)
# ---------------------------------------------------------------------------
CHEM = {
    "24CH201T": ("Introduction to Artificial Intelligence", "ESC", 3, 0, 0, 3),
    "24CH202T": ("Chemical Process Calculations", "PC", 3, 1, 0, 4),
    "24CH203T": ("Mechanical Unit Operations", "PC", 3, 0, 0, 3),
    "24CH203P": ("Mechanical Unit Operations Lab", "PC", 0, 0, 2, 1),
    "24CH204T": ("Fluid Mechanics", "PC", 3, 0, 0, 3),
    "24CH204P": ("Fluid Mechanics Lab", "PC", 0, 0, 2, 1),
    "24CH205T": ("Chemical Engineering Industry 4.0", "ESC", 2, 0, 0, 2),
    "24CH205P": ("Chemical Engineering Industry 4.0 Lab", "ESC", 0, 0, 2, 1),
    "24CH206T": ("Introduction to Numerical Methods for Chemical Engineers", "PC", 3, 1, 0, 4),
    "24CH207T": ("Chemical Engineering Thermodynamics", "PC", 3, 0, 0, 3),
    "24CH207P": ("Chemical Engineering Thermodynamics Lab", "PC", 0, 0, 2, 1),
    "24CH208T": ("Heat Transfer", "PC", 3, 0, 0, 3),
    "24CH208P": ("Heat Transfer Lab", "PC", 0, 0, 2, 1),
    "24CH209T": ("Chemical Process Technology", "PC", 3, 0, 0, 3),
    "24CH209P": ("Chemical Process Technology Lab", "PC", 0, 0, 2, 1),
    "24CH301T": ("Mass Transfer 1", "PC", 3, 0, 0, 3),
    "24CH301P": ("Mass Transfer 1 Lab", "PC", 0, 0, 2, 1),
    "24CH302T": ("Chemical Reaction Engineering 1", "PC", 3, 0, 0, 3),
    "24CH302P": ("Chemical Reaction Engineering 1 Lab", "PC", 0, 0, 2, 1),
    "24CH303T": ("Process Equipment Design", "PC", 3, 0, 0, 3),
    "24CH303P": ("Process Equipment Design Lab", "PC", 0, 0, 2, 1),
    "24CH304T": ("Instrumentation & Process Control", "PC", 3, 0, 0, 3),
    "24CH304P": ("Instrumentation & Process Control Lab", "PC", 0, 0, 2, 1),
    "24CH305T": ("Mass Transfer 2", "PC", 3, 0, 0, 3),
    "24CH305P": ("Mass Transfer 2 Lab", "PC", 0, 0, 2, 1),
    "24CH306T": ("Chemical Reaction Engineering 2", "PC", 3, 0, 0, 3),
    "24CH306P": ("Chemical Reaction Engineering 2 Lab", "PC", 0, 0, 2, 1),
    "24CH401T": ("Process Modelling and Optimization", "PC", 3, 0, 0, 3),
    "24CH401P": ("Process Modelling and Optimization Lab", "PC", 0, 0, 2, 1),
    "24CH402T": ("Computer Aided Process Design", "PC", 3, 0, 0, 3),
    "24CH402P": ("Computer Aided Process Design Lab", "PC", 0, 0, 2, 1),
    "24CH403T": ("Transport Phenomenon", "PC", 3, 1, 0, 4),
    "24PRCH451": ("Seminar", "PRO", 0, 0, 0, 0),
    "24PRCH452": ("Major/Comprehensive Project", "PRO", 0, 0, 26, 13),
    "24CH331T": ("Petroleum Refining & Petrochemicals", "PE", 3, 0, 0, 3),
    "24CH332T": ("Renewable Energy Engineering", "PE", 3, 0, 0, 3),
    "24CH333T": ("Sustainability & Green Chemistry", "PE", 3, 0, 0, 3),
    "24CH334T": ("Piping Design", "PE", 3, 0, 0, 3),
    "24CH335T": ("Corrosion Engineering", "PE", 3, 0, 0, 3),
    "24CH336T": ("Material Science & Engineering", "PE", 3, 0, 0, 3),
    "24CH337T": ("Nano Technology & Energy Storage", "PE", 3, 0, 0, 3),
    "24CH338T": ("Membrane Processes", "PE", 3, 0, 0, 3),
    "24CH339T": ("Environmental Engineering and Pollution Control", "PE", 3, 0, 0, 3),
    "24CH431T": ("Polymer Science & Technology", "PE", 3, 0, 0, 3),
    "24CH432T": ("Energy Conversion Device Engineering", "PE", 3, 0, 0, 3),
    "24CH433T": ("Pharmaceuticals Technology", "PE", 3, 0, 0, 3),
    "24CH434T": ("Process Plant Safety, Health and Hygiene", "PE", 3, 0, 0, 3),
    "24CH435T": ("Project Management", "PE", 3, 0, 0, 3),
    "24CH436T": ("Plant Design & Process Economics", "PE", 3, 0, 0, 3),
}

SUBJECTS = {}
for _block in (SHARED, CS, ICT, ECE, MECH, CIVIL, CHEM):
    SUBJECTS.update(_block)

# ---------------------------------------------------------------------------
# Curriculum: dept_code -> semester -> [subject_code, ...]
# ---------------------------------------------------------------------------
CURRICULUM = {
    "CP": {
        1: ["24HS101T", "24MA101T", "24PH102T", "24PH102P", "24CV101T", "24ME101P",
            "24ME102P", "24CP101T", "24CP101P", "24HS102T", "24HS103T"],
        2: ["24HS105T", "24MA103T", "24CH101T", "24CH101P", "24EE101T", "24EE101P",
            "24BT101T", "24YOG101", "24NCC101", "24NSS101", "24HS104T", "24CP102T", "24CP102P"],
        3: ["24INT151", "24MA202T", "24CS201T", "24CS201P", "24CS202T", "24CS203T",
            "24CS203P", "24CS204T", "24CS204P"],
        4: ["24OE201T", "24CS205P", "24CS206T", "24CS207T", "24CS208T", "24CS208P",
            "24CS209T", "24CS210T", "24CS210P"],
        5: ["MOOC", "24CS301T", "24HS301T", "24CS331T", "24CS302T", "24CS302P",
            "24CS303T", "24CS303P", "24CS304T", "24CS304P"],
        6: ["24OE301T", "24CS336T", "24CS341T", "24CS305T", "24CS305P", "24CS306T",
            "24CS306P", "24CS307T", "24CS307P"],
        7: ["24INT451", "24OE401T", "24CS401T", "24CS401P", "24CS431T", "24CS436T",
            "24CS402T", "24CS402P", "24CS403T", "24PRCS451"],
        8: ["24PRCS452"],
    },
    "IT": {
        1: ["24HS101T", "24MA101T", "24PH102T", "24PH102P", "24CV101T", "24ME101P",
            "24BT102T", "24CP101T", "24CP101P", "24HS102T", "24HS103T"],
        2: ["24HS105T", "24MA103T", "24CH101T", "24CH101P", "24EE101T", "24EE101P",
            "24ME102P", "24YOG101", "24NCC101", "24NSS101", "24HS104T", "24CP102T", "24CP102P"],
        3: ["24INT151", "24IT201T", "24IT202T", "24IT202P", "24IT203T", "24IT203P",
            "24IT204T", "24IT205T", "24MA202T"],
        4: ["24IT206T", "24IT206P", "24OE201T", "24IT207T", "24IT207P", "24IT208T",
            "24IT208P", "24IT209T", "24IT210T", "24IT210P"],
        5: ["MOOC", "24HS301T", "24IT331T", "24IT301T", "24IT301P", "24IT302T",
            "24IT302P", "24IT303T", "24IT303P"],
        6: ["24OE301T", "24IT335T", "24IT338T", "24IT304T", "24IT304P", "24IT305T",
            "24IT305P", "24IT306T", "24IT306P"],
        7: ["24INT451", "24OE401T", "24IT431T", "24IT434T", "24IT401T", "24IT401P",
            "24IT402T", "24IT402P", "24IT403T", "24IT403P", "24PRIT451"],
        8: ["24PRIT452"],
    },
    "EC": {
        1: ["24HS101T", "24MA101T", "24PH101T", "24PH101P", "24CV101T", "24ME101P",
            "24BT102T", "24CP101T", "24CP101P", "24HS102T", "24HS103T"],
        2: ["24HS105T", "24MA103T", "24CH101T", "24CH101P", "24EE101T", "24EE101P",
            "24ME102P", "24YOG101", "24NCC101", "24NSS101", "24HS104T", "24CP102T", "24CP102P"],
        3: ["24INT151", "24EC201T", "24EC202T", "24EC202P", "24EC203T", "24EC203P",
            "24EC204T", "24MA201T"],
        4: ["24EC205T", "24EC205P", "24OE201T", "24EC206T", "24EC206P", "24EC207T",
            "24EC207P", "24EC208T", "24EC209T", "24EC209P"],
        5: ["MOOC", "24HS301T", "24EC331T", "24EC301T", "24EC301P", "24EC302T",
            "24EC302P", "24EC303T", "24EC303P"],
        6: ["24OE301T", "24EC333T", "24EC337T", "24EC304T", "24EC304P", "24EC305T",
            "24EC305P", "24EC306T", "24EC306P"],
        7: ["24INT451", "24OE401T", "24EC431T", "24EC436T", "24EC401T", "24EC401P",
            "24EC402T", "24EC402P", "24EC403T", "24EC403P", "24PREC451"],
        8: ["24PREC452"],
    },
    "ME": {
        1: ["24MA101T", "24PH102T", "24PH102P", "24BT102T", "24CV101T", "24CP101T",
            "24CP101P", "24ME101P", "24ME102P", "24HS101T", "24HS102T"],
        2: ["24MA103T", "24CH101T", "24CH101P", "24CP102T", "24CP102P", "24EE101T",
            "24EE101P", "24HS103T", "24HS104T", "24HS105T", "24YOG101", "24NSS101", "24NCC101"],
        3: ["24INT151", "24MA201T", "24ME201T", "24ME202T", "24ME203T", "24ME203P",
            "24ME204T", "24ME204P", "24ME205P"],
        4: ["24ME221T", "24ME205T", "24ME205P", "24ME206T", "24ME206P", "24ME207T",
            "24ME207P", "24ME208T", "24ME208P", "24ME209T", "24ME209P", "24INT251"],
        5: ["24HS301T", "MOOC", "24ME331T", "24ME301T", "24ME301P", "24ME302T",
            "24ME302P", "24ME303T", "24ME303P"],
        6: ["24OE301T", "24ME335T", "24ME304T", "24ME304P", "24ME305T", "24ME305P",
            "24ME306T", "24ME306P", "24ME307T", "24ME307P"],
        7: ["24INT451", "24OE401T", "24ME431T", "24ME434T", "24ME436T", "24ME401T",
            "24ME402T", "24ME403P", "24PRME451"],
        8: ["24PRME452", "24PRME453"],
    },
    "CE": {
        1: ["24HS101T", "24MA101T", "24PH102T", "24PH102P", "24CV101T", "24ME101P",
            "24BT102T", "24CP101T", "24CP101P", "24HS102T", "24HS103T"],
        2: ["24HS105T", "24MA103T", "24CH101T", "24CH101P", "24EE101T", "24EE101P",
            "24ME102P", "24YOG101", "24NCC101", "24NSS101", "24HS104T", "24CP102T", "24CP102P"],
        3: ["24INT151", "24MA201T", "24CV201T", "24CV202T", "24CV203T", "24CV204T",
            "24CV205T", "24CV206P"],
        4: ["24CV207T", "24CV207P", "24OE201T", "24CV208T", "24CV209T", "24CV210T",
            "24CV211T", "24INT251"],
        5: ["MOOC", "24HS301T", "24CV331T", "24CV301T", "24CV302T", "24CV303T", "24CV304P"],
        6: ["24OE301T", "24CV332T", "24CV333T", "24CV305T", "24CV306P", "24CV307T", "24CV308T"],
        7: ["24INT451", "24OE401T", "24CV431T", "24CV432T", "24CV401T", "24CV402T",
            "24CV403T", "24PRCV451"],
        8: ["24PRCV452"],
    },
    "CH": {
        1: ["24MA101T", "24HS101T", "24CP101T", "24CP101P", "24CH101T", "24CH101P",
            "24EE101T", "24EE101P", "24BT101T", "24HS104T", "24YOG101", "24NSS101", "24NCC101"],
        2: ["24HS105T", "24MA103T", "24CP102T", "24CP102P", "24PH103T", "24PH103P",
            "24ME101P", "24ME102P", "24CV101T", "24HS102T", "24HS103T"],
        3: ["24INT151", "24MA201T", "24CH201T", "24CH202T", "24CH203T", "24CH203P",
            "24CH204T", "24CH204P"],
        4: ["24INT251", "24OE201T", "24CH205T", "24CH205P", "24CH206T", "24CH207T",
            "24CH207P", "24CH208T", "24CH208P", "24CH209T", "24CH209P"],
        5: ["MOOC", "24HS301T", "24CH331T", "24CH301T", "24CH301P", "24CH302T",
            "24CH302P", "24CH303T", "24CH303P"],
        6: ["24OE301T", "24CH334T", "24CH337T", "24CH304T", "24CH304P", "24CH305T",
            "24CH305P", "24CH306T", "24CH306P"],
        7: ["24INT451", "24OE401T", "24CH431T", "24CH434T", "24CH401T", "24CH401P",
            "24CH402T", "24CH402P", "24CH403T", "24PRCH451"],
        8: ["24PRCH452"],
    },
}


def component(subject_code: str) -> str:
    """Theory vs Lab, from the trailing T/P of the printed code convention."""
    name = SUBJECTS[subject_code][0]
    if subject_code.endswith("P"):
        return "Lab"
    if subject_code.endswith("T"):
        return "Theory"
    # 24INT151 / 24PRME452 / 24YOG101 / MOOC style codes
    if any(word in name for word in ("Laboratory", "Lab")):
        return "Lab"
    return "Theory"


# Subject-area codes each department owns and staffs. Shared first-year service
# courses (MA/PH/BT/HS/EE) are delivered by basic-science and humanities departments
# that this dataset does not model, so no branch faculty is assigned to them.
OWNED_AREAS = {
    "CP": {"CS", "CP"},   # CS also owns the Computer Programming service course
    "IT": {"IT"},
    "EC": {"EC"},
    "ME": {"ME"},         # ME also owns Workshop Practices / Engineering Graphics
    "CE": {"CV"},         # Civil also owns Environmental Science
    "CH": {"CH"},         # Chemical also owns Engineering Chemistry
}

_AREA_RE = __import__("re").compile(r"^24([A-Z]+)\d")


def subject_area(subject_code: str) -> str:
    m = _AREA_RE.match(subject_code)
    return m.group(1) if m else ""


def teachable_subjects(dept_code: str, semester: int):
    """Subjects a faculty member of this department could actually be assigned.

    Excludes internships, seminars, projects and MOOC/open-elective placeholders,
    and service courses owned by another department.
    """
    out = []
    for code in CURRICULUM[dept_code][semester]:
        name, category, *_ = SUBJECTS[code]
        if category in ("PRO", "OE") or code == "MOOC":
            continue
        if subject_area(code) not in OWNED_AREAS[dept_code]:
            continue
        out.append(code)
    return out
