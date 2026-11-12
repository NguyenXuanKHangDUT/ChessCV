-- ============================================================
-- PBL4 ChessCV
-- Database initialization
-- MySQL 8.x
-- ============================================================


-- ============================================================
-- DATABASE
-- ============================================================

CREATE DATABASE IF NOT EXISTS chesscv
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;


USE chesscv;


-- ============================================================
-- TABLE: players
-- ============================================================

CREATE TABLE IF NOT EXISTS players (
    id INT NOT NULL AUTO_INCREMENT,

    name VARCHAR(100) NOT NULL,

    created_at DATETIME NOT NULL,

    PRIMARY KEY (id),

    INDEX ix_players_name (name)
)
ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- TABLE: games
-- ============================================================

CREATE TABLE IF NOT EXISTS games (
    id INT NOT NULL AUTO_INCREMENT,


    -- ========================================================
    -- PLAYERS
    -- ========================================================

    white_player_id INT NULL,

    black_player_id INT NULL,


    -- ========================================================
    -- BOARD STATE
    -- ========================================================

    initial_fen VARCHAR(255) NOT NULL,

    final_fen VARCHAR(255) NULL,

    pgn TEXT NULL,


    -- ========================================================
    -- RESULT
    -- ========================================================

    result VARCHAR(20) NOT NULL,

    termination VARCHAR(50) NULL,


    -- ========================================================
    -- OPENING
    -- ========================================================

    opening_name VARCHAR(255) NULL,

    eco_code VARCHAR(10) NULL,


    -- ========================================================
    -- MOVE COUNT
    -- ========================================================

    total_moves INT NOT NULL,


    -- ========================================================
    -- TIME
    -- ========================================================

    started_at DATETIME NULL,

    ended_at DATETIME NULL,

    created_at DATETIME NOT NULL,


    -- ========================================================
    -- PRIMARY KEY
    -- ========================================================

    PRIMARY KEY (id),


    -- ========================================================
    -- INDEXES
    -- ========================================================

    INDEX ix_games_white_player_id (
        white_player_id
    ),

    INDEX ix_games_black_player_id (
        black_player_id
    ),


    -- ========================================================
    -- FOREIGN KEYS
    -- ========================================================

    CONSTRAINT fk_games_white_player
        FOREIGN KEY (
            white_player_id
        )
        REFERENCES players(id)
        ON DELETE SET NULL,

    CONSTRAINT fk_games_black_player
        FOREIGN KEY (
            black_player_id
        )
        REFERENCES players(id)
        ON DELETE SET NULL
)
ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- TABLE: moves
-- ============================================================

CREATE TABLE IF NOT EXISTS moves (
    id INT NOT NULL AUTO_INCREMENT,


    -- ========================================================
    -- GAME
    -- ========================================================

    game_id INT NOT NULL,


    -- ========================================================
    -- MOVE NUMBERING
    -- ========================================================
    --
    -- Example:
    --
    -- 1. e4
    --    ply         = 1
    --    move_number = 1
    --    color       = white
    --
    -- 1... e5
    --    ply         = 2
    --    move_number = 1
    --    color       = black
    --
    -- ========================================================

    ply INT NOT NULL,

    move_number INT NOT NULL,

    color VARCHAR(10) NOT NULL,


    -- ========================================================
    -- MOVE NOTATION
    -- ========================================================
    --
    -- UCI:
    -- e2e4
    --
    -- SAN:
    -- e4
    -- Nf3
    -- O-O
    -- Qh7#
    --
    -- ========================================================

    uci VARCHAR(10) NOT NULL,

    san VARCHAR(30) NOT NULL,


    -- ========================================================
    -- BOARD STATE
    -- ========================================================

    fen_before VARCHAR(255) NOT NULL,

    fen_after VARCHAR(255) NOT NULL,


    -- ========================================================
    -- TIME
    -- ========================================================

    created_at DATETIME NOT NULL,


    -- ========================================================
    -- PRIMARY KEY
    -- ========================================================

    PRIMARY KEY (id),


    -- ========================================================
    -- INDEX
    -- ========================================================

    INDEX ix_moves_game_id (
        game_id
    ),


    -- ========================================================
    -- FOREIGN KEY
    -- ========================================================

    CONSTRAINT fk_moves_game
        FOREIGN KEY (
            game_id
        )
        REFERENCES games(id)
        ON DELETE CASCADE
)
ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- VERIFY
-- ============================================================

SHOW TABLES;


DESCRIBE players;

DESCRIBE games;

DESCRIBE moves;