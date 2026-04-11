CREATE TABLE User (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    email VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    phone VARCHAR(15),
    address TEXT,
    date_of_birth DATE,
    avatar_url TEXT,
    account_status ENUM('active','suspended') DEFAULT 'active'
);

CREATE TABLE Admin (
    admin_id INT AUTO_INCREMENT PRIMARY KEY,
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    gender VARCHAR(10),
    salary DECIMAL(10,2),
    aadhaar VARCHAR(20) UNIQUE,
    email VARCHAR(100) UNIQUE,
    password VARCHAR(255) NOT NULL,
    phone VARCHAR(15),
    address TEXT
);

CREATE TABLE Channel (
    channel_id INT AUTO_INCREMENT PRIMARY KEY,
    channel_name VARCHAR(100),
    description TEXT,
    avatar_url TEXT,
    creation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id INT UNIQUE,
    FOREIGN KEY (user_id) REFERENCES User(user_id) ON DELETE CASCADE
);

CREATE TABLE Video (
    video_id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200),
    description TEXT,
    thumbnail_url TEXT,
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    duration INT,
    format VARCHAR(20),
    visibility ENUM('public','private') DEFAULT 'public',
    views_count INT DEFAULT 0,
    drive_link TEXT,
    channel_id INT,
    FOREIGN KEY (channel_id) REFERENCES Channel(channel_id) ON DELETE CASCADE
);

CREATE TABLE Tag (
    tag_id INT AUTO_INCREMENT PRIMARY KEY,
    tag_name VARCHAR(50) UNIQUE
);

CREATE TABLE Video_Tag (
    video_id INT,
    tag_id INT,
    PRIMARY KEY (video_id, tag_id),
    FOREIGN KEY (video_id) REFERENCES Video(video_id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES Tag(tag_id) ON DELETE CASCADE
);

CREATE TABLE Like_Table (
    user_id INT,
    video_id INT,
    liked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, video_id),
    FOREIGN KEY (user_id) REFERENCES User(user_id) ON DELETE CASCADE,
    FOREIGN KEY (video_id) REFERENCES Video(video_id) ON DELETE CASCADE
);

CREATE TABLE Subscription (
    user_id INT,
    channel_id INT,
    subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, channel_id),
    FOREIGN KEY (user_id) REFERENCES User(user_id) ON DELETE CASCADE,
    FOREIGN KEY (channel_id) REFERENCES Channel(channel_id) ON DELETE CASCADE
);

CREATE TABLE Comment (
    comment_id INT AUTO_INCREMENT PRIMARY KEY,
    content TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id INT,
    video_id INT,
    FOREIGN KEY (user_id) REFERENCES User(user_id) ON DELETE CASCADE,
    FOREIGN KEY (video_id) REFERENCES Video(video_id) ON DELETE CASCADE
);

CREATE TABLE Playlist (
    playlist_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100),
    creation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    visibility ENUM('public','private') DEFAULT 'public',
    user_id INT,
    FOREIGN KEY (user_id) REFERENCES User(user_id) ON DELETE CASCADE
);

CREATE TABLE Playlist_Video (
    playlist_id INT,
    video_id INT,
    PRIMARY KEY (playlist_id, video_id),
    FOREIGN KEY (playlist_id) REFERENCES Playlist(playlist_id) ON DELETE CASCADE,
    FOREIGN KEY (video_id) REFERENCES Video(video_id) ON DELETE CASCADE
);

CREATE TABLE Watch_History (
    user_id INT,
    video_id INT,
    watch_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    watch_duration INT,
    PRIMARY KEY (user_id, video_id, watch_timestamp),
    FOREIGN KEY (user_id) REFERENCES User(user_id) ON DELETE CASCADE,
    FOREIGN KEY (video_id) REFERENCES Video(video_id) ON DELETE CASCADE
);

CREATE TABLE Ticket (
    ticket_id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200),
    description TEXT,
    category VARCHAR(50),
    date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status ENUM('new','in-process','resolved') DEFAULT 'new',
    resolution_description TEXT,
    user_id INT,
    admin_id INT,
    FOREIGN KEY (user_id) REFERENCES User(user_id) ON DELETE CASCADE,
    FOREIGN KEY (admin_id) REFERENCES Admin(admin_id) ON DELETE SET NULL
);