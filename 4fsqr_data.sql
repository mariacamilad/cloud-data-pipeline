CREATE TABLE datos_externos (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR(150) NOT NULL,
    address    VARCHAR(255),
    categories JSONB,
    latitude   DOUBLE PRECISION,
    longitude  DOUBLE PRECISION,
    distance   INTEGER
);
