CREATE TABLE players (
    player_id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    rank VARCHAR(20),
    toxicity_points INT DEFAULT 0
);

CREATE TABLE queue (
    queue_id SERIAL PRIMARY KEY,
    player_id INT REFERENCES players(player_id),
    join_time TIMESTAMP DEFAULT NOW()
);

CREATE TABLE matches (
    match_id SERIAL PRIMARY KEY,
    player_id INT REFERENCES players(player_id),
    team VARCHAR(10),
    match_date TIMESTAMP DEFAULT NOW()
);
