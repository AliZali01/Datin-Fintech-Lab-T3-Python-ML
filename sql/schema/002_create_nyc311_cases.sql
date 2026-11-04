
CREATE TABLE IF NOT EXISTS nyc311.cases (

    -- Primary key
    unique_key VARCHAR(20) PRIMARY KEY,

    -- Dates
    created_date TIMESTAMP NOT NULL,
    closed_date TIMESTAMP,
    resolution_action_updated_date TIMESTAMP,

    -- Complaint information
    agency TEXT,
    agency_name TEXT,
    complaint_type TEXT NOT NULL,
    descriptor TEXT,
    status TEXT,

    -- Borough and location information
    community_board TEXT,
    police_precinct TEXT,
    borough TEXT,
    open_data_channel_type TEXT,
    park_facility_name TEXT,
    park_borough TEXT,
    location_type TEXT,
    incident_address TEXT,
    street_name TEXT,
    address_type TEXT,
    resolution_description TEXT,

    -- Address details
    incident_zip VARCHAR(10),
    cross_street_2 TEXT,
    intersection_street_2 TEXT,
    cross_street_1 TEXT,
    intersection_street_1 TEXT,

    -- Coordinates
    y_coordinate_state_plane DOUBLE PRECISION,
    x_coordinate_state_plane DOUBLE PRECISION,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    location TEXT,

    -- Additional information
    council_district SMALLINT,
    city TEXT,
    landmark TEXT,
    bbl VARCHAR(20),

    -- Derived columns
    resolution_time_hours NUMERIC(14, 6),
    created_year SMALLINT NOT NULL,
    created_month SMALLINT NOT NULL,
    created_year_month CHAR(7) NOT NULL,

    -- Population enrichment
    population_estimate INTEGER,
    population_match_status TEXT,

    -- Constraints
    CONSTRAINT chk_created_month
        CHECK (created_month BETWEEN 1 AND 12),

    CONSTRAINT chk_resolution_time
        CHECK (
            resolution_time_hours IS NULL
            OR resolution_time_hours >= 0
        ),

    CONSTRAINT chk_latitude
        CHECK (
            latitude IS NULL
            OR latitude BETWEEN -90 AND 90
        ),

    CONSTRAINT chk_longitude
        CHECK (
            longitude IS NULL
            OR longitude BETWEEN -180 AND 180
        ),

    CONSTRAINT chk_population
        CHECK (
            population_estimate IS NULL
            OR population_estimate >= 0
        ),

    CONSTRAINT chk_closed_date
        CHECK (
            closed_date IS NULL
            OR closed_date >= created_date
        )
);
