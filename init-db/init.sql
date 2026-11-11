SET FOREIGN_KEY_CHECKS=0;

-- ============================================
-- Table structure for table `AdminUsers`
-- ============================================
CREATE TABLE `AdminUsers` (
  `Id` int NOT NULL AUTO_INCREMENT,
  `Firstname` varchar(45) NOT NULL,
  `Lastname` varchar(45) NOT NULL,
  `Email` varchar(256) NOT NULL,
  `SchoolId` int DEFAULT NULL COMMENT 'NULL for system and competition admins',
  `PasswordHash` varchar(255) DEFAULT NULL,
  `IsLocked` tinyint(1) NOT NULL DEFAULT 0,
  `Role` tinyint(1) NOT NULL DEFAULT 0 COMMENT '0 teacher, 1 system admin, 2 competition admin',
  `Question1` varchar(255) DEFAULT NULL,
  `Question2` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`Id`),
  UNIQUE KEY `adminusers_email_unique` (`Email`),
  KEY `fk_adminusers_school_idx` (`SchoolId`),
  CONSTRAINT `chk_adminusers_role` CHECK (`Role` IN (0, 1, 2))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================
-- Table structure for table `CompetitionAdminDivisions`
-- Which divisions each competition admin (AdminUsers.Role = 2) covers
-- ============================================
CREATE TABLE `CompetitionAdminDivisions` (
  `Id` int NOT NULL AUTO_INCREMENT,
  `AdminId` int NOT NULL,
  `Division` varchar(5) COLLATE utf8mb4_bin NOT NULL COMMENT 'Blue, Gold, or Eagle. Match Teams.Division',
  PRIMARY KEY (`Id`),
  UNIQUE KEY `uq_admin_division` (`AdminId`, `Division`),
  CONSTRAINT `chk_cad_division` CHECK (`Division` IN ('Blue', 'Gold', 'Eagle'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================
-- Table structure for table `LoginAttempts`
-- ============================================
CREATE TABLE `LoginAttempts` (
  `Id` int NOT NULL AUTO_INCREMENT,
  `Time` datetime NOT NULL,
  `IPAddress` varchar(39) NOT NULL,
  `Email` varchar(256) NOT NULL,
  PRIMARY KEY (`Id`),
  KEY `idx_loginattempts_email` (`Email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================
-- Table structure for table `Projects`
-- ============================================
CREATE TABLE `Projects` (
  `Id` int NOT NULL AUTO_INCREMENT COMMENT 'Table to keep track of projects',
  `Name` varchar(1000) NOT NULL,
  `Language` varchar(45) NOT NULL,
  `Type` varchar(20) NOT NULL,
  `Division` varchar(20) NOT NULL DEFAULT 'blue',
  `GoldProblemType` varchar(20) NOT NULL DEFAULT 'normal',
  `DescriptionText` text,
  `OrderIndex` int DEFAULT NULL,
  `solutionpath` varchar(1000) DEFAULT NULL,
  `AsnDescriptionPath` varchar(1000) DEFAULT NULL,
  `AdditionalFilePath` varchar(200) DEFAULT NULL,
  PRIMARY KEY (`Id`),
  UNIQUE KEY `idProjects_UNIQUE` (`Id`),
  KEY `idx_projects_type_orderindex` (`Type`,`OrderIndex`),
  KEY `idx_projects_type_division_orderindex` (`Type`,`Division`,`OrderIndex`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================
-- Table structure for table `Schools`
-- ============================================
CREATE TABLE `Schools` (
  `Id` int NOT NULL AUTO_INCREMENT,
  `Name` varchar(256) NOT NULL,
  PRIMARY KEY (`Id`),
  UNIQUE KEY `schools_name_unique` (`Name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================
-- Table structure for table `Teams`
-- ============================================
CREATE TABLE `Teams` (
  `Id` int NOT NULL AUTO_INCREMENT,
  `SchoolId` int NOT NULL,
  `TeamNumber` int NOT NULL,
  `Name` varchar(45) NOT NULL,
  `Division` varchar(5) DEFAULT NULL,
  `IsOnline` tinyint(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`Id`),
  KEY `fk_teams_school_idx` (`SchoolId`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================
-- Table structure for table `StudentUsers`
-- ============================================
CREATE TABLE `StudentUsers` (
  `Id` int NOT NULL AUTO_INCREMENT,
  `EmailHash` char(64) NOT NULL,
  `TeacherId` int NOT NULL,
  `SchoolId` int NOT NULL,
  `TeamId` int NOT NULL,
  `MemberId` int DEFAULT NULL,
  `PasswordHash` varchar(255) DEFAULT NULL,
  `IsLocked` tinyint(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`Id`),
  UNIQUE KEY `studentusers_emailhash_unique` (`EmailHash`),
  KEY `fk_studentusers_teacher_idx` (`TeacherId`),
  KEY `fk_studentusers_school_idx` (`SchoolId`),
  KEY `fk_studentusers_team_idx` (`TeamId`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================
-- Table structure for table `Submissions`
-- ============================================
CREATE TABLE `Submissions` (
  `Id` int NOT NULL AUTO_INCREMENT COMMENT 'Table to keep track of submissions from users',
  `Team` int NOT NULL,
  `User` int NOT NULL,
  `Time` datetime NOT NULL,
  `OutputFilepath` varchar(256) NOT NULL,
  `Project` int NOT NULL,
  `CodeFilepath` varchar(256) NOT NULL,
  `IsPassing` tinyint(1) NOT NULL,
  `TestCaseResults` text,
  PRIMARY KEY (`Id`),
  UNIQUE KEY `idSubmissions_UNIQUE` (`Id`),
  KEY `idx_submissions_team` (`Team`),
  KEY `idx_submissions_user` (`User`),
  KEY `idx_submissions_project` (`Project`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================
-- Table structure for table `Testcases`
-- ============================================
CREATE TABLE `Testcases` (
  `Id` int NOT NULL AUTO_INCREMENT,
  `ProjectId` int DEFAULT NULL,
  `Name` text,
  `Description` text,
  `input` text,
  `Output` text,
  `Hidden` tinyint(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`Id`),
  UNIQUE KEY `Id_UNIQUE` (`Id`),
  KEY `tc_fk_idx` (`ProjectId`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================
-- Table structure for table `GoldDivision`
-- ============================================
CREATE TABLE `GoldDivision` (
  `Id` int NOT NULL AUTO_INCREMENT,
  `Link` text NOT NULL,
  `DocLink` varchar(1000) DEFAULT NULL,
  `StudentId` int NOT NULL,
  `ProjectId` int NOT NULL,
  `SubmittedAt` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `Points` int,
  `Feedback` text,
  `AdminGraderId` int,
  `RegradeRequestedAt` datetime DEFAULT NULL,
  `RegradeRequestedByStudentId` int DEFAULT NULL,
  PRIMARY KEY (`Id`),
  KEY `idx_golddivision_studentid` (`StudentId`),
  KEY `idx_golddivision_projectid` (`ProjectId`),
  KEY `idx_golddivision_team_lookup` (`ProjectId`,`SubmittedAt`,`Id`),
  KEY `idx_golddivision_admingraderid` (`AdminGraderId`),
  KEY `idx_golddivision_regraderequestedat` (`RegradeRequestedAt`),
  KEY `idx_golddivision_regraderequestedbystudentid` (`RegradeRequestedByStudentId`),
  CONSTRAINT `fk_golddivision_student`
    FOREIGN KEY (`StudentId`) REFERENCES `StudentUsers`(`Id`) ON DELETE CASCADE,
  CONSTRAINT `fk_golddivision_project`
    FOREIGN KEY (`ProjectId`) REFERENCES `Projects`(`Id`) ON DELETE CASCADE,
  CONSTRAINT `fk_golddivision_admingrader`
    FOREIGN KEY (`AdminGraderId`) REFERENCES `AdminUsers`(`Id`) ON DELETE SET NULL,
  CONSTRAINT `fk_golddivision_regrade_student`
    FOREIGN KEY (`RegradeRequestedByStudentId`) REFERENCES `StudentUsers`(`Id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Table structure for table `HelpRequests`
-- ============================================
CREATE TABLE HelpRequests (
    Id int NOT NULL AUTO_INCREMENT,
    StudentId int,
    TeacherId int,
    ProblemId int,
    Reason varchar(255) NOT NULL,
    Description text,
    Status int NOT NULL,
    CurrentAdminId int,
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CompletedAt TIMESTAMP NULL,
    PRIMARY KEY (`Id`),
    UNIQUE KEY `Id_UNIQUE` (`Id`),
    FOREIGN KEY (`StudentId`) REFERENCES StudentUsers(Id) ON DELETE CASCADE,
    FOREIGN KEY (`TeacherId`) REFERENCES AdminUsers(Id) ON DELETE SET NULL,
    FOREIGN KEY (`CurrentAdminId`) REFERENCES AdminUsers(Id) ON DELETE SET NULL,
    FOREIGN KEY (`ProblemId`) REFERENCES Projects(Id) ON DELETE SET NULL
)ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE HelpRequestMessages (
    Id int NOT NULL AUTO_INCREMENT,
    HelpRequestId int NOT NULL,
    SenderType varchar(16) NOT NULL,
    StudentId int DEFAULT NULL,
    AdminId int DEFAULT NULL,
    Body text NOT NULL,
    CreatedAt datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`Id`),
    KEY `idx_helprequestmessages_request` (`HelpRequestId`),
    KEY `idx_helprequestmessages_created` (`CreatedAt`),
    CONSTRAINT `fk_helprequestmessages_request`
      FOREIGN KEY (`HelpRequestId`) REFERENCES `HelpRequests` (`Id`) ON DELETE CASCADE,
    CONSTRAINT `fk_helprequestmessages_student`
      FOREIGN KEY (`StudentId`) REFERENCES `StudentUsers` (`Id`) ON DELETE SET NULL,
    CONSTRAINT `fk_helprequestmessages_admin`
      FOREIGN KEY (`AdminId`) REFERENCES `AdminUsers` (`Id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `EagleTeamMessages` (
  `Id` int NOT NULL AUTO_INCREMENT,
  `TeamId` int NOT NULL,
  `SenderType` varchar(16) NOT NULL,
  `StudentId` int DEFAULT NULL,
  `AdminId` int DEFAULT NULL,
  `Body` text NOT NULL,
  `CreatedAt` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`Id`),
  KEY `idx_eagle_msg_team` (`TeamId`),
  KEY `idx_eagle_msg_created` (`CreatedAt`),
  CONSTRAINT `fk_eagle_msg_team` FOREIGN KEY (`TeamId`) REFERENCES `Teams` (`Id`) ON DELETE CASCADE,
  CONSTRAINT `fk_eagle_msg_student` FOREIGN KEY (`StudentId`) REFERENCES `StudentUsers` (`Id`) ON DELETE SET NULL,
  CONSTRAINT `fk_eagle_msg_admin` FOREIGN KEY (`AdminId`) REFERENCES `AdminUsers` (`Id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================
-- Table structure for table `TeamProjectStats`
-- ============================================
CREATE TABLE `TeamProjectStats` (
  `Id` int NOT NULL AUTO_INCREMENT,
  `TeamId` int NOT NULL,
  `ProjectId` int NOT NULL,
  `Attempts` int NOT NULL DEFAULT 0,
  `Solved` tinyint(1) NOT NULL DEFAULT 0,
  `AcceptedTimeMinutes` int DEFAULT NULL,
  `CurrentSubmissionId` int NOT NULL,
  PRIMARY KEY (`Id`),
  UNIQUE KEY `teamprojectstats_team_project_unique` (`TeamId`,`ProjectId`),
  KEY `fk_teamprojectstats_team_idx` (`TeamId`),
  KEY `fk_teamprojectstats_project_idx` (`ProjectId`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================
-- Table structure for table `ScoreboardSnapshots`
-- ============================================
CREATE TABLE `ScoreboardSnapshots` (
  `Id` int NOT NULL AUTO_INCREMENT,
  `Division` varchar(5) NOT NULL,
  `IsOnline` tinyint(1) NOT NULL,
  `Minute` int NOT NULL,
  `TimeStamp` datetime NOT NULL,
  `Payload` text NOT NULL,
  PRIMARY KEY (`Id`),
  UNIQUE KEY `scoreboardsnapshots_division_online_minute_unique` (`Division`,`IsOnline`,`Minute`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================
-- Foreign keys (added after all tables exist)
-- ============================================

ALTER TABLE `AdminUsers`
  ADD CONSTRAINT `fk_adminusers_school`
  FOREIGN KEY (`SchoolId`) REFERENCES `Schools` (`Id`);

ALTER TABLE `CompetitionAdminDivisions`
  ADD CONSTRAINT `fk_cad_admin`
  FOREIGN KEY (`AdminId`) REFERENCES `AdminUsers` (`Id`)
  ON DELETE CASCADE;

ALTER TABLE `StudentUsers`
  ADD CONSTRAINT `fk_studentusers_teacher`
  FOREIGN KEY (`TeacherId`) REFERENCES `AdminUsers` (`Id`);

ALTER TABLE `StudentUsers`
  ADD CONSTRAINT `fk_studentusers_school`
  FOREIGN KEY (`SchoolId`) REFERENCES `Schools` (`Id`);

ALTER TABLE `StudentUsers`
  ADD CONSTRAINT `fk_studentusers_team`
  FOREIGN KEY (`TeamId`) REFERENCES `Teams` (`Id`);

ALTER TABLE `Teams`
  ADD CONSTRAINT `fk_teams_school`
  FOREIGN KEY (`SchoolId`) REFERENCES `Schools` (`Id`);

ALTER TABLE `Submissions`
  ADD CONSTRAINT `fk_submissions_team`
  FOREIGN KEY (`Team`) REFERENCES `Teams` (`Id`);

ALTER TABLE `Submissions`
  ADD CONSTRAINT `fk_submissions_student`
  FOREIGN KEY (`User`) REFERENCES `StudentUsers` (`Id`);

ALTER TABLE `Submissions`
  ADD CONSTRAINT `fk_submissions_project`
  FOREIGN KEY (`Project`) REFERENCES `Projects` (`Id`);

ALTER TABLE `Testcases`
  ADD CONSTRAINT `tc_fk`
  FOREIGN KEY (`ProjectId`) REFERENCES `Projects` (`Id`);

ALTER TABLE `TeamProjectStats`
  ADD CONSTRAINT `fk_teamprojectstats_team`
  FOREIGN KEY (`TeamId`) REFERENCES `Teams` (`Id`)
  ON DELETE CASCADE;

ALTER TABLE `TeamProjectStats`
  ADD CONSTRAINT `fk_teamprojectstats_project`
  FOREIGN KEY (`ProjectId`) REFERENCES `Projects` (`Id`)
  ON DELETE CASCADE;

-- ============================================
-- Seed Schools data
-- ============================================
INSERT INTO `Schools` (`Name`) VALUES
  ('Belleville High School'),
  ('Brookfield Academy'),
  ('Brookfield Central High School'),
  ('Cedarburg High School'),
  ('Craig High School'),
  ('De Pere High School'),
  ('Franklin High School'),
  ('High School of the Health Sciences'),
  ('Homestead High School'),
  ('Johnson Creek Schools'),
  ('Kettle Moraine High School'),
  ('Menomonee Falls High School'),
  ('New London High School'),
  ('Oak Creek High School'),
  ('Parker High School'),
  ('Reagan IB High School'),
  ('Reedsburg Area High School'),
  ('Rufus King High School'),
  ('Sauk Prairie High School'),
  ('St. Francis High School'),
  ('West De Pere High School');

SET FOREIGN_KEY_CHECKS=1;