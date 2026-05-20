CREATE DATABASE  IF NOT EXISTS `apms_db` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci */ /*!80016 DEFAULT ENCRYPTION='N' */;
USE `apms_db`;
-- MySQL dump 10.13  Distrib 8.0.45, for Win64 (x86_64)
--
-- Host: localhost    Database: apms_db
-- ------------------------------------------------------
-- Server version	8.0.45

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `ai_conversations`
--

DROP TABLE IF EXISTS `ai_conversations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ai_conversations` (
  `conv_id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `session_id` varchar(120) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Client-generated conversation session ID',
  `message_role` enum('user','assistant') COLLATE utf8mb4_unicode_ci NOT NULL,
  `message_text` mediumtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`conv_id`),
  KEY `idx_ai_user_session` (`user_id`,`session_id`,`created_at`),
  KEY `idx_ai_created` (`created_at`),
  CONSTRAINT `ai_conversations_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `ai_conversations`
--

LOCK TABLES `ai_conversations` WRITE;
/*!40000 ALTER TABLE `ai_conversations` DISABLE KEYS */;
/*!40000 ALTER TABLE `ai_conversations` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `announcements`
--

DROP TABLE IF EXISTS `announcements`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `announcements` (
  `announcement_id` int NOT NULL AUTO_INCREMENT,
  `message` text NOT NULL,
  `activation_url` varchar(500) NOT NULL DEFAULT '/activate',
  `created_by` int NOT NULL COMMENT 'head_of_department user_id',
  `expires_at` date NOT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`announcement_id`),
  KEY `created_by` (`created_by`),
  CONSTRAINT `announcements_ibfk_1` FOREIGN KEY (`created_by`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `announcements`
--

LOCK TABLES `announcements` WRITE;
/*!40000 ALTER TABLE `announcements` DISABLE KEYS */;
INSERT INTO `announcements` VALUES (1,'Account activation is now open.Click the link to set your password.\nRegards,\nHead of department.','/activate',1,'2026-06-11',1,'2026-05-20 13:13:52');
/*!40000 ALTER TABLE `announcements` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `challenges_reflections`
--

DROP TABLE IF EXISTS `challenges_reflections`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `challenges_reflections` (
  `challenge_id` int NOT NULL AUTO_INCREMENT,
  `project_id` int NOT NULL,
  `student_id` int NOT NULL COMMENT 'user_id',
  `type` enum('technical','administrative','reflection') COLLATE utf8mb4_unicode_ci NOT NULL,
  `title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Short title for the challenge or reflection',
  `description` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `solution_lesson` text COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`challenge_id`),
  KEY `project_id` (`project_id`),
  KEY `student_id` (`student_id`),
  CONSTRAINT `challenges_reflections_ibfk_1` FOREIGN KEY (`project_id`) REFERENCES `projects` (`project_id`) ON DELETE CASCADE,
  CONSTRAINT `challenges_reflections_ibfk_2` FOREIGN KEY (`student_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `challenges_reflections`
--

LOCK TABLES `challenges_reflections` WRITE;
/*!40000 ALTER TABLE `challenges_reflections` DISABLE KEYS */;
/*!40000 ALTER TABLE `challenges_reflections` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `committee_members`
--

DROP TABLE IF EXISTS `committee_members`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `committee_members` (
  `cm_id` int NOT NULL AUTO_INCREMENT,
  `committee_id` int NOT NULL,
  `faculty_id` int NOT NULL,
  `role` enum('supervisor','member','chair') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'member',
  `evaluation_score` decimal(5,2) DEFAULT NULL,
  `evaluation_comments` text COLLATE utf8mb4_unicode_ci,
  `evaluation_submitted` tinyint(1) NOT NULL DEFAULT '0',
  `evaluation_submitted_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`cm_id`),
  UNIQUE KEY `uq_committee_faculty` (`committee_id`,`faculty_id`),
  KEY `faculty_id` (`faculty_id`),
  CONSTRAINT `committee_members_ibfk_1` FOREIGN KEY (`committee_id`) REFERENCES `committees` (`committee_id`) ON DELETE CASCADE,
  CONSTRAINT `committee_members_ibfk_2` FOREIGN KEY (`faculty_id`) REFERENCES `faculty` (`faculty_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=31 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `committee_members`
--

LOCK TABLES `committee_members` WRITE;
/*!40000 ALTER TABLE `committee_members` DISABLE KEYS */;
/*!40000 ALTER TABLE `committee_members` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `committee_plan_members`
--

DROP TABLE IF EXISTS `committee_plan_members`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `committee_plan_members` (
  `id` int NOT NULL AUTO_INCREMENT,
  `plan_id` int NOT NULL,
  `faculty_id` int NOT NULL,
  `role` enum('member','supervisor','responsible') NOT NULL DEFAULT 'member',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_committee_plan_member` (`plan_id`,`faculty_id`),
  KEY `faculty_id` (`faculty_id`),
  CONSTRAINT `committee_plan_members_ibfk_1` FOREIGN KEY (`plan_id`) REFERENCES `committee_plans` (`plan_id`) ON DELETE CASCADE,
  CONSTRAINT `committee_plan_members_ibfk_2` FOREIGN KEY (`faculty_id`) REFERENCES `faculty` (`faculty_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `committee_plan_members`
--

LOCK TABLES `committee_plan_members` WRITE;
/*!40000 ALTER TABLE `committee_plan_members` DISABLE KEYS */;
/*!40000 ALTER TABLE `committee_plan_members` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `committee_plan_projects`
--

DROP TABLE IF EXISTS `committee_plan_projects`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `committee_plan_projects` (
  `id` int NOT NULL AUTO_INCREMENT,
  `plan_id` int NOT NULL,
  `project_id` int NOT NULL,
  `slot_order` int NOT NULL,
  `slot_start` time NOT NULL,
  `slot_end` time NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_committee_plan_project` (`plan_id`,`project_id`),
  UNIQUE KEY `uq_unique_project_committee` (`project_id`),
  CONSTRAINT `committee_plan_projects_ibfk_1` FOREIGN KEY (`plan_id`) REFERENCES `committee_plans` (`plan_id`) ON DELETE CASCADE,
  CONSTRAINT `committee_plan_projects_ibfk_2` FOREIGN KEY (`project_id`) REFERENCES `projects` (`project_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `committee_plan_projects`
--

LOCK TABLES `committee_plan_projects` WRITE;
/*!40000 ALTER TABLE `committee_plan_projects` DISABLE KEYS */;
/*!40000 ALTER TABLE `committee_plan_projects` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `committee_plans`
--

DROP TABLE IF EXISTS `committee_plans`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `committee_plans` (
  `plan_id` int NOT NULL AUTO_INCREMENT,
  `committee_name` varchar(150) NOT NULL,
  `academic_year` varchar(20) NOT NULL,
  `discussion_date` date NOT NULL,
  `start_time` time NOT NULL,
  `end_time` time NOT NULL,
  `room_id` int NOT NULL,
  `responsible_faculty_id` int DEFAULT NULL,
  `final_average` decimal(5,2) DEFAULT NULL,
  `status` enum('draft','scheduled','completed','cancelled') NOT NULL DEFAULT 'draft',
  `created_by` int NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`plan_id`),
  KEY `room_id` (`room_id`),
  KEY `responsible_faculty_id` (`responsible_faculty_id`),
  KEY `created_by` (`created_by`),
  CONSTRAINT `committee_plans_ibfk_1` FOREIGN KEY (`room_id`) REFERENCES `discussion_rooms` (`room_id`),
  CONSTRAINT `committee_plans_ibfk_2` FOREIGN KEY (`responsible_faculty_id`) REFERENCES `faculty` (`faculty_id`) ON DELETE SET NULL,
  CONSTRAINT `committee_plans_ibfk_3` FOREIGN KEY (`created_by`) REFERENCES `users` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `committee_plans`
--

LOCK TABLES `committee_plans` WRITE;
/*!40000 ALTER TABLE `committee_plans` DISABLE KEYS */;
/*!40000 ALTER TABLE `committee_plans` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `committees`
--

DROP TABLE IF EXISTS `committees`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `committees` (
  `committee_id` int NOT NULL AUTO_INCREMENT,
  `project_id` int NOT NULL,
  `committee_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `discussion_date` date NOT NULL,
  `discussion_time` time DEFAULT NULL,
  `room` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status` enum('scheduled','in_progress','completed','cancelled') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'scheduled',
  `final_average` decimal(5,2) DEFAULT NULL COMMENT 'Average score from all committee members',
  `created_by` int NOT NULL COMMENT 'coordinator user_id',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`committee_id`),
  UNIQUE KEY `project_id` (`project_id`),
  KEY `created_by` (`created_by`),
  CONSTRAINT `committees_ibfk_1` FOREIGN KEY (`project_id`) REFERENCES `projects` (`project_id`) ON DELETE CASCADE,
  CONSTRAINT `committees_ibfk_2` FOREIGN KEY (`created_by`) REFERENCES `users` (`user_id`)
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `committees`
--

LOCK TABLES `committees` WRITE;
/*!40000 ALTER TABLE `committees` DISABLE KEYS */;
INSERT INTO `committees` VALUES (4,1,'APMS Evaluation Committee','2026-02-20','10:00:00','A101','scheduled',NULL,2,'2026-05-20 13:45:01'),(5,4,'AI Disease Recognition Evaluation Committee','2025-02-21','14:00:00','B203','completed',92.30,2,'2026-05-20 13:45:01'),(6,5,'E-Learning Platform Evaluation Committee','2024-02-22','10:00:00','C105','completed',87.00,2,'2026-05-20 13:45:01');
/*!40000 ALTER TABLE `committees` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `comp4200_timeline_items`
--

DROP TABLE IF EXISTS `comp4200_timeline_items`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `comp4200_timeline_items` (
  `item_id` int NOT NULL AUTO_INCREMENT,
  `timeline_id` int NOT NULL,
  `item_order` int NOT NULL DEFAULT '1',
  `title` varchar(180) NOT NULL,
  `description` text,
  `start_date` date DEFAULT NULL,
  `start_time` varchar(5) DEFAULT NULL,
  `due_date` date DEFAULT NULL,
  `due_time` varchar(5) DEFAULT NULL,
  `milestone_label` varchar(180) DEFAULT NULL,
  `is_deadline` tinyint(1) NOT NULL DEFAULT '1',
  `is_archived` tinyint(1) NOT NULL DEFAULT '0',
  `submitted_to` varchar(20) NOT NULL DEFAULT 'supervisor',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`item_id`),
  KEY `idx_comp4200_timeline_items_due` (`due_date`),
  KEY `idx_comp4200_timeline_items_order` (`timeline_id`,`item_order`),
  CONSTRAINT `comp4200_timeline_items_ibfk_1` FOREIGN KEY (`timeline_id`) REFERENCES `comp4200_timelines` (`timeline_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `comp4200_timeline_items`
--

LOCK TABLES `comp4200_timeline_items` WRITE;
/*!40000 ALTER TABLE `comp4200_timeline_items` DISABLE KEYS */;
/*!40000 ALTER TABLE `comp4200_timeline_items` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `comp4200_timelines`
--

DROP TABLE IF EXISTS `comp4200_timelines`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `comp4200_timelines` (
  `timeline_id` int NOT NULL AUTO_INCREMENT,
  `semester_id` int NOT NULL,
  `title` varchar(180) NOT NULL DEFAULT 'Project Introduction Timeline',
  `note` text,
  `is_published` tinyint(1) NOT NULL DEFAULT '0',
  `published_at` datetime DEFAULT NULL,
  `created_by` int DEFAULT NULL,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`timeline_id`),
  UNIQUE KEY `semester_id` (`semester_id`),
  KEY `created_by` (`created_by`),
  CONSTRAINT `comp4200_timelines_ibfk_1` FOREIGN KEY (`semester_id`) REFERENCES `semesters` (`semester_id`) ON DELETE CASCADE,
  CONSTRAINT `comp4200_timelines_ibfk_2` FOREIGN KEY (`created_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `comp4200_timelines`
--

LOCK TABLES `comp4200_timelines` WRITE;
/*!40000 ALTER TABLE `comp4200_timelines` DISABLE KEYS */;
/*!40000 ALTER TABLE `comp4200_timelines` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `coordinator_assignments`
--

DROP TABLE IF EXISTS `coordinator_assignments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `coordinator_assignments` (
  `assignment_id` int NOT NULL AUTO_INCREMENT,
  `faculty_id` int NOT NULL COMMENT 'Assigned coordinator faculty_id',
  `semester_id` int NOT NULL,
  `assigned_by` int NOT NULL COMMENT 'Head of department user_id',
  `notes` text COLLATE utf8mb4_unicode_ci,
  `assigned_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`assignment_id`),
  UNIQUE KEY `uq_coordinator_semester` (`semester_id`),
  KEY `faculty_id` (`faculty_id`),
  KEY `assigned_by` (`assigned_by`),
  CONSTRAINT `coordinator_assignments_ibfk_1` FOREIGN KEY (`faculty_id`) REFERENCES `faculty` (`faculty_id`),
  CONSTRAINT `coordinator_assignments_ibfk_2` FOREIGN KEY (`semester_id`) REFERENCES `semesters` (`semester_id`),
  CONSTRAINT `coordinator_assignments_ibfk_3` FOREIGN KEY (`assigned_by`) REFERENCES `users` (`user_id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `coordinator_assignments`
--

LOCK TABLES `coordinator_assignments` WRITE;
/*!40000 ALTER TABLE `coordinator_assignments` DISABLE KEYS */;
INSERT INTO `coordinator_assignments` VALUES (1,2,1,1,'Official coordinator for Semester 1 — 2025/2026','2026-05-20 13:03:29'),(2,5,5,1,'Coordinator for COMP4300 — 2025/2026 Semester 2','2026-05-20 13:03:29');
/*!40000 ALTER TABLE `coordinator_assignments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `coordinator_decisions`
--

DROP TABLE IF EXISTS `coordinator_decisions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `coordinator_decisions` (
  `decision_id` int NOT NULL AUTO_INCREMENT,
  `project_id` int NOT NULL,
  `coordinator_id` int NOT NULL COMMENT 'user_id',
  `decision` enum('accepted','rejected','needs_revision','send_to_committee') COLLATE utf8mb4_unicode_ci NOT NULL,
  `notes` text COLLATE utf8mb4_unicode_ci,
  `decided_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`decision_id`),
  KEY `project_id` (`project_id`),
  KEY `coordinator_id` (`coordinator_id`),
  CONSTRAINT `coordinator_decisions_ibfk_1` FOREIGN KEY (`project_id`) REFERENCES `projects` (`project_id`) ON DELETE CASCADE,
  CONSTRAINT `coordinator_decisions_ibfk_2` FOREIGN KEY (`coordinator_id`) REFERENCES `users` (`user_id`)
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `coordinator_decisions`
--

LOCK TABLES `coordinator_decisions` WRITE;
/*!40000 ALTER TABLE `coordinator_decisions` DISABLE KEYS */;
INSERT INTO `coordinator_decisions` VALUES (5,4,2,'send_to_committee','Project accepted and forwarded to committee evaluation after a satisfactory initial review.','2026-05-20 13:45:01'),(6,5,2,'accepted','Excellent project — archiving completed successfully.','2026-05-20 13:45:01'),(7,7,2,'rejected','Project score is below the minimum required threshold of 60%.','2026-05-20 13:45:01'),(8,6,2,'needs_revision','Student must add a security and privacy section and clarify the patient data protection protocol.','2026-05-20 13:45:01'),(9,4,2,'send_to_committee','Project accepted and forwarded to committee evaluation after a satisfactory initial review.','2026-05-20 13:57:21'),(10,5,2,'accepted','Excellent project — archiving completed successfully.','2026-05-20 13:57:21'),(11,7,2,'rejected','Project score is below the minimum required threshold of 60%.','2026-05-20 13:57:21'),(12,6,2,'needs_revision','Student must add a security and privacy section and clarify the patient data protection protocol.','2026-05-20 13:57:21');
/*!40000 ALTER TABLE `coordinator_decisions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `coordinator_deliverable_submissions`
--

DROP TABLE IF EXISTS `coordinator_deliverable_submissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `coordinator_deliverable_submissions` (
  `submission_id` int NOT NULL AUTO_INCREMENT,
  `deliverable_id` int NOT NULL,
  `project_id` int DEFAULT NULL,
  `student_id` int NOT NULL,
  `file_name` varchar(255) NOT NULL,
  `file_path` varchar(600) DEFAULT NULL,
  `file_data` longblob,
  `file_mime` varchar(120) DEFAULT NULL,
  `file_size_mb` decimal(7,2) DEFAULT NULL,
  `submitted_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `status` enum('submitted','late','reviewed') NOT NULL DEFAULT 'submitted',
  `notes` text,
  PRIMARY KEY (`submission_id`),
  UNIQUE KEY `uq_deliverable_student` (`deliverable_id`,`student_id`),
  KEY `project_id` (`project_id`),
  KEY `student_id` (`student_id`),
  CONSTRAINT `coordinator_deliverable_submissions_ibfk_1` FOREIGN KEY (`deliverable_id`) REFERENCES `coordinator_deliverables` (`deliverable_id`) ON DELETE CASCADE,
  CONSTRAINT `coordinator_deliverable_submissions_ibfk_2` FOREIGN KEY (`project_id`) REFERENCES `projects` (`project_id`) ON DELETE SET NULL,
  CONSTRAINT `coordinator_deliverable_submissions_ibfk_3` FOREIGN KEY (`student_id`) REFERENCES `students` (`student_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `coordinator_deliverable_submissions`
--

LOCK TABLES `coordinator_deliverable_submissions` WRITE;
/*!40000 ALTER TABLE `coordinator_deliverable_submissions` DISABLE KEYS */;
/*!40000 ALTER TABLE `coordinator_deliverable_submissions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `coordinator_deliverables`
--

DROP TABLE IF EXISTS `coordinator_deliverables`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `coordinator_deliverables` (
  `deliverable_id` int NOT NULL AUTO_INCREMENT,
  `semester_id` int DEFAULT NULL,
  `course_scope` enum('introduction','graduation_project') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'introduction',
  `title` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text COLLATE utf8mb4_unicode_ci,
  `due_date` date DEFAULT NULL,
  `mark_points` decimal(5,2) NOT NULL DEFAULT '0.00',
  `status` enum('not_open','open','in_progress','completed','closed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'not_open',
  `created_by` int DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`deliverable_id`),
  KEY `idx_coord_deliverables_semester_scope` (`semester_id`,`course_scope`),
  CONSTRAINT `fk_coord_deliverables_semester` FOREIGN KEY (`semester_id`) REFERENCES `semesters` (`semester_id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `coordinator_deliverables`
--

LOCK TABLES `coordinator_deliverables` WRITE;
/*!40000 ALTER TABLE `coordinator_deliverables` DISABLE KEYS */;
/*!40000 ALTER TABLE `coordinator_deliverables` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `coordinator_lectures`
--

DROP TABLE IF EXISTS `coordinator_lectures`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `coordinator_lectures` (
  `lecture_id` int NOT NULL AUTO_INCREMENT,
  `semester_id` int DEFAULT NULL,
  `course_scope` enum('introduction','graduation_project') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'introduction',
  `title` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text COLLATE utf8mb4_unicode_ci,
  `lecture_date` date DEFAULT NULL,
  `week_label` varchar(80) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status` enum('scheduled','completed','cancelled') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'scheduled',
  `created_by` int DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`lecture_id`),
  KEY `idx_coord_lectures_semester_scope` (`semester_id`,`course_scope`),
  CONSTRAINT `fk_coord_lectures_semester` FOREIGN KEY (`semester_id`) REFERENCES `semesters` (`semester_id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `coordinator_lectures`
--

LOCK TABLES `coordinator_lectures` WRITE;
/*!40000 ALTER TABLE `coordinator_lectures` DISABLE KEYS */;
/*!40000 ALTER TABLE `coordinator_lectures` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `deadlines`
--

DROP TABLE IF EXISTS `deadlines`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `deadlines` (
  `deadline_id` int NOT NULL AUTO_INCREMENT,
  `semester_id` int NOT NULL,
  `project_id` int DEFAULT NULL COMMENT 'NULL = applies to whole semester',
  `deadline_type` varchar(120) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'e.g. final_report_submission',
  `deadline_date` date NOT NULL,
  `description` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`deadline_id`),
  KEY `semester_id` (`semester_id`),
  KEY `project_id` (`project_id`),
  CONSTRAINT `deadlines_ibfk_1` FOREIGN KEY (`semester_id`) REFERENCES `semesters` (`semester_id`) ON DELETE CASCADE,
  CONSTRAINT `deadlines_ibfk_2` FOREIGN KEY (`project_id`) REFERENCES `projects` (`project_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=19 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `deadlines`
--

LOCK TABLES `deadlines` WRITE;
/*!40000 ALTER TABLE `deadlines` DISABLE KEYS */;
INSERT INTO `deadlines` VALUES (1,1,NULL,'project_registration','2026-02-15','Deadline for all project registrations'),(2,1,NULL,'file_submission','2026-02-15','Deadline for uploading all required project files'),(3,1,NULL,'results_announcement','2026-02-28','Final results announcement date'),(7,1,NULL,'project_registration','2026-02-15','Deadline for all project registrations'),(8,1,NULL,'file_submission','2026-02-15','Deadline for uploading all required project files'),(9,1,NULL,'results_announcement','2026-02-28','Final results announcement date'),(10,1,1,'final_report_submission','2026-02-15','Final report submission deadline — APMS project'),(11,1,1,'committee_discussion','2026-02-20','APMS project committee discussion date'),(12,1,1,'supervisor_feedback','2026-02-08','Deadline for supervisor feedback on APMS report'),(13,1,NULL,'project_registration','2026-02-15','Deadline for all project registrations'),(14,1,NULL,'file_submission','2026-02-15','Deadline for uploading all required project files'),(15,1,NULL,'results_announcement','2026-02-28','Final results announcement date'),(16,1,1,'final_report_submission','2026-02-15','Final report submission deadline — APMS project'),(17,1,1,'committee_discussion','2026-02-20','APMS project committee discussion date'),(18,1,1,'supervisor_feedback','2026-02-08','Deadline for supervisor feedback on APMS report');
/*!40000 ALTER TABLE `deadlines` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `discussion_rooms`
--

DROP TABLE IF EXISTS `discussion_rooms`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `discussion_rooms` (
  `room_id` int NOT NULL AUTO_INCREMENT,
  `room_name` varchar(120) NOT NULL,
  `sort_order` int NOT NULL DEFAULT '1',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`room_id`),
  UNIQUE KEY `room_name` (`room_name`)
) ENGINE=InnoDB AUTO_INCREMENT=28 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `discussion_rooms`
--

LOCK TABLES `discussion_rooms` WRITE;
/*!40000 ALTER TABLE `discussion_rooms` DISABLE KEYS */;
INSERT INTO `discussion_rooms` VALUES (1,'Room 201 — Faculty of Engineering',1,1),(2,'Room 202 — Faculty of Engineering',1,1),(3,'Room 203 — Faculty of Engineering',1,1),(4,'Room 204 — Faculty of Engineering',1,1),(5,'Room 201 — Engineering Building',1,1),(6,'Room 202 — Engineering Building',2,1),(7,'Room 203 — Engineering Building',3,1),(8,'Room 204 — Engineering Building',4,1),(9,'Lab 1 — Computer Science',5,1),(10,'Lab 2 — Computer Science',6,1),(11,'Hall A — New Building',7,1),(12,'Hall B — New Building',8,1);
/*!40000 ALTER TABLE `discussion_rooms` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `faculty`
--

DROP TABLE IF EXISTS `faculty`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `faculty` (
  `faculty_id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `specialization` enum('software_engineering','artificial_intelligence','web_development','mobile','security_networks','databases','other') COLLATE utf8mb4_unicode_ci NOT NULL,
  `years_experience` tinyint unsigned DEFAULT '0',
  `title` varchar(30) COLLATE utf8mb4_unicode_ci DEFAULT 'Dr.' COMMENT 'Academic title (e.g. Dr., Prof.)',
  `office_number` varchar(120) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`faculty_id`),
  UNIQUE KEY `user_id` (`user_id`),
  CONSTRAINT `faculty_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=53 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `faculty`
--

LOCK TABLES `faculty` WRITE;
/*!40000 ALTER TABLE `faculty` DISABLE KEYS */;
INSERT INTO `faculty` VALUES (1,1,'software_engineering',15,'Dr.','Science Building — 214'),(2,2,'web_development',10,'Dr.','Science Building — 214'),(3,3,'software_engineering',8,'Dr.','Science Building — 214'),(4,4,'software_engineering',8,'Dr.','Science Building — 214'),(5,5,'databases',8,'Dr.','Science Building — 214'),(6,6,'mobile',8,'Dr.','Science Building — 214'),(7,7,'security_networks',8,'Dr.','Science Building — 214'),(8,18,'databases',8,'Dr.','Science Building — 214'),(9,19,'software_engineering',8,'Dr.','Science Building — 214'),(10,20,'web_development',8,'Dr.','Science Building — 214'),(11,21,'databases',8,'Dr.','Science Building — 214'),(12,22,'software_engineering',8,'Dr.','Science Building — 214'),(13,23,'software_engineering',8,'Dr.','Science Building — 214'),(14,24,'software_engineering',8,'Dr.','Science Building — 214'),(15,25,'software_engineering',8,'Dr.','Science Building — 214'),(16,26,'mobile',8,'Dr.','Science Building — 214'),(17,27,'web_development',8,'Dr.','Science Building — 214'),(18,28,'artificial_intelligence',8,'Dr.','Science Building — 214'),(19,29,'software_engineering',8,'Dr.','Science Building — 214'),(20,30,'software_engineering',8,'Dr.','Science Building — 214'),(21,31,'software_engineering',8,'Dr.','Science Building — 214'),(22,32,'artificial_intelligence',8,'Dr.','Science Building — 214'),(23,33,'security_networks',8,'Dr.','Science Building — 214');
/*!40000 ALTER TABLE `faculty` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `faculty_load_settings`
--

DROP TABLE IF EXISTS `faculty_load_settings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `faculty_load_settings` (
  `load_id` int NOT NULL AUTO_INCREMENT,
  `faculty_id` int NOT NULL,
  `semester_id` int NOT NULL,
  `graduation_project_hours` decimal(5,2) NOT NULL DEFAULT '0.00',
  `min_hours` decimal(5,2) NOT NULL DEFAULT '12.00',
  `max_hours` decimal(5,2) NOT NULL DEFAULT '36.00',
  `employment_type` enum('full_time','part_time') NOT NULL DEFAULT 'full_time',
  `intro_students` int NOT NULL DEFAULT '0',
  `extra_bonus` decimal(5,2) NOT NULL DEFAULT '0.00',
  `assigned_courses` text,
  `updated_by` int DEFAULT NULL,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`load_id`),
  UNIQUE KEY `uq_faculty_semester_load` (`faculty_id`,`semester_id`),
  KEY `semester_id` (`semester_id`),
  KEY `updated_by` (`updated_by`),
  CONSTRAINT `faculty_load_settings_ibfk_1` FOREIGN KEY (`faculty_id`) REFERENCES `faculty` (`faculty_id`) ON DELETE CASCADE,
  CONSTRAINT `faculty_load_settings_ibfk_2` FOREIGN KEY (`semester_id`) REFERENCES `semesters` (`semester_id`) ON DELETE CASCADE,
  CONSTRAINT `faculty_load_settings_ibfk_3` FOREIGN KEY (`updated_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `faculty_load_settings`
--

LOCK TABLES `faculty_load_settings` WRITE;
/*!40000 ALTER TABLE `faculty_load_settings` DISABLE KEYS */;
/*!40000 ALTER TABLE `faculty_load_settings` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `feedback`
--

DROP TABLE IF EXISTS `feedback`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `feedback` (
  `feedback_id` int NOT NULL AUTO_INCREMENT,
  `project_id` int NOT NULL,
  `reviewer_id` int NOT NULL COMMENT 'Reviewer user_id',
  `feedback_type` enum('final_report_review','source_code_review','general_performance','discussion_notes','follow_up','committee_evaluation') COLLATE utf8mb4_unicode_ci NOT NULL,
  `feedback_text` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `score` decimal(5,2) DEFAULT NULL COMMENT 'Score out of 100',
  `priority` enum('normal','important','urgent') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'normal',
  `is_draft` tinyint(1) NOT NULL DEFAULT '0',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`feedback_id`),
  KEY `idx_feedback_project` (`project_id`),
  KEY `idx_feedback_reviewer` (`reviewer_id`),
  CONSTRAINT `feedback_ibfk_1` FOREIGN KEY (`project_id`) REFERENCES `projects` (`project_id`) ON DELETE CASCADE,
  CONSTRAINT `feedback_ibfk_2` FOREIGN KEY (`reviewer_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `feedback`
--

LOCK TABLES `feedback` WRITE;
/*!40000 ALTER TABLE `feedback` DISABLE KEYS */;
INSERT INTO `feedback` VALUES (5,1,3,'final_report_review','The report is generally well-written. I recommend clarifying the system architecture section further and adding detailed ERD diagrams. Please also ensure consistent use of technical terminology across all chapters.',78.00,'important',0,'2026-05-20 13:45:01'),(6,1,4,'committee_evaluation','The AI section needs more detail, particularly regarding the chatbot training methodology and accuracy evaluation. I recommend adding a comparison table of the NLP models used.',75.00,'normal',0,'2026-05-20 13:45:01'),(7,1,5,'committee_evaluation','The proposed UI is well thought out and appropriate. I recommend addressing accessibility requirements (WCAG) and adding support for users with special needs.',82.00,'normal',0,'2026-05-20 13:45:01'),(8,2,4,'source_code_review','The code is well-structured, but you need to add documentation comments to all major functions and write unit tests for sensitive operations such as authentication and role checking.',71.00,'normal',0,'2026-05-20 13:45:01'),(9,1,3,'final_report_review','The report is generally well-written. I recommend clarifying the system architecture section further and adding detailed ERD diagrams. Please also ensure consistent use of technical terminology across all chapters.',78.00,'important',0,'2026-05-20 13:57:21'),(10,1,4,'committee_evaluation','The AI section needs more detail, particularly regarding the chatbot training methodology and accuracy evaluation. I recommend adding a comparison table of the NLP models used.',75.00,'normal',0,'2026-05-20 13:57:21'),(11,1,5,'committee_evaluation','The proposed UI is well thought out and appropriate. I recommend addressing accessibility requirements (WCAG) and adding support for users with special needs.',82.00,'normal',0,'2026-05-20 13:57:21'),(12,2,4,'source_code_review','The code is well-structured, but you need to add documentation comments to all major functions and write unit tests for sensitive operations such as authentication and role checking.',71.00,'normal',0,'2026-05-20 13:57:21');
/*!40000 ALTER TABLE `feedback` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `feedback_improvement_points`
--

DROP TABLE IF EXISTS `feedback_improvement_points`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `feedback_improvement_points` (
  `point_id` int NOT NULL AUTO_INCREMENT,
  `feedback_id` int NOT NULL,
  `point_text` varchar(600) COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_resolved` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`point_id`),
  KEY `feedback_id` (`feedback_id`),
  CONSTRAINT `feedback_improvement_points_ibfk_1` FOREIGN KEY (`feedback_id`) REFERENCES `feedback` (`feedback_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=19 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `feedback_improvement_points`
--

LOCK TABLES `feedback_improvement_points` WRITE;
/*!40000 ALTER TABLE `feedback_improvement_points` DISABLE KEYS */;
/*!40000 ALTER TABLE `feedback_improvement_points` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `final_decisions`
--

DROP TABLE IF EXISTS `final_decisions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `final_decisions` (
  `decision_id` int NOT NULL AUTO_INCREMENT,
  `project_id` int NOT NULL,
  `coordinator_id` int NOT NULL COMMENT 'user_id',
  `decision` enum('accepted','rejected') COLLATE utf8mb4_unicode_ci NOT NULL,
  `final_score` decimal(5,2) DEFAULT NULL,
  `notes` text COLLATE utf8mb4_unicode_ci,
  `decided_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `is_archived` tinyint(1) NOT NULL DEFAULT '0',
  `archived_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`decision_id`),
  UNIQUE KEY `project_id` (`project_id`),
  KEY `coordinator_id` (`coordinator_id`),
  CONSTRAINT `final_decisions_ibfk_1` FOREIGN KEY (`project_id`) REFERENCES `projects` (`project_id`) ON DELETE CASCADE,
  CONSTRAINT `final_decisions_ibfk_2` FOREIGN KEY (`coordinator_id`) REFERENCES `users` (`user_id`)
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `final_decisions`
--

LOCK TABLES `final_decisions` WRITE;
/*!40000 ALTER TABLE `final_decisions` DISABLE KEYS */;
INSERT INTO `final_decisions` VALUES (4,4,2,'accepted',92.30,'Outstanding project — archived successfully.','2026-05-20 13:45:01',1,'2025-03-01 07:00:00'),(5,5,2,'accepted',87.00,'Very good project — archived successfully.','2026-05-20 13:45:01',1,'2024-03-01 07:00:00'),(6,7,2,'rejected',54.00,'Score below minimum threshold — student notified.','2026-05-20 13:45:01',0,NULL);
/*!40000 ALTER TABLE `final_decisions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `grade_entries`
--

DROP TABLE IF EXISTS `grade_entries`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `grade_entries` (
  `entry_id` int NOT NULL AUTO_INCREMENT,
  `session_id` int NOT NULL,
  `faculty_id` int NOT NULL,
  `project_id` int DEFAULT NULL,
  `section_id` int DEFAULT NULL,
  `grade_type` enum('report_reader','coordinator','supervisor','discussion_member','committee_member') COLLATE utf8mb4_unicode_ci NOT NULL,
  `max_mark` decimal(5,2) NOT NULL,
  `mark` decimal(5,2) DEFAULT NULL,
  `comments` text COLLATE utf8mb4_unicode_ci,
  `submitted_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`entry_id`),
  UNIQUE KEY `uq_grade_entry` (`session_id`,`faculty_id`,`grade_type`),
  KEY `faculty_id` (`faculty_id`),
  KEY `project_id` (`project_id`),
  KEY `section_id` (`section_id`),
  CONSTRAINT `grade_entries_ibfk_1` FOREIGN KEY (`session_id`) REFERENCES `grade_entry_sessions` (`session_id`) ON DELETE CASCADE,
  CONSTRAINT `grade_entries_ibfk_2` FOREIGN KEY (`faculty_id`) REFERENCES `faculty` (`faculty_id`) ON DELETE CASCADE,
  CONSTRAINT `grade_entries_ibfk_3` FOREIGN KEY (`project_id`) REFERENCES `projects` (`project_id`) ON DELETE CASCADE,
  CONSTRAINT `grade_entries_ibfk_4` FOREIGN KEY (`section_id`) REFERENCES `student_distribution_sections` (`section_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `grade_entries`
--

LOCK TABLES `grade_entries` WRITE;
/*!40000 ALTER TABLE `grade_entries` DISABLE KEYS */;
/*!40000 ALTER TABLE `grade_entries` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `grade_entry_sessions`
--

DROP TABLE IF EXISTS `grade_entry_sessions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `grade_entry_sessions` (
  `session_id` int NOT NULL AUTO_INCREMENT,
  `project_id` int DEFAULT NULL,
  `section_id` int DEFAULT NULL,
  `course_scope` enum('introduction','graduation_project') COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` enum('closed','open','completed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'open',
  `opened_by` int NOT NULL,
  `opened_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `closed_at` datetime DEFAULT NULL,
  PRIMARY KEY (`session_id`),
  KEY `project_id` (`project_id`),
  KEY `section_id` (`section_id`),
  KEY `opened_by` (`opened_by`),
  CONSTRAINT `grade_entry_sessions_ibfk_1` FOREIGN KEY (`project_id`) REFERENCES `projects` (`project_id`) ON DELETE CASCADE,
  CONSTRAINT `grade_entry_sessions_ibfk_2` FOREIGN KEY (`section_id`) REFERENCES `student_distribution_sections` (`section_id`) ON DELETE CASCADE,
  CONSTRAINT `grade_entry_sessions_ibfk_3` FOREIGN KEY (`opened_by`) REFERENCES `users` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `grade_entry_sessions`
--

LOCK TABLES `grade_entry_sessions` WRITE;
/*!40000 ALTER TABLE `grade_entry_sessions` DISABLE KEYS */;
/*!40000 ALTER TABLE `grade_entry_sessions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `notifications`
--

DROP TABLE IF EXISTS `notifications`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `notifications` (
  `notification_id` int NOT NULL AUTO_INCREMENT,
  `recipient_id` int NOT NULL COMMENT 'user_id',
  `sender_id` int DEFAULT NULL COMMENT 'user_id or NULL for system',
  `notification_type` enum('file_uploaded','feedback_received','committee_assigned','deadline_reminder','project_reviewed','status_changed','supervisor_assigned','urgent_alert','system') COLLATE utf8mb4_unicode_ci NOT NULL,
  `title` varchar(250) COLLATE utf8mb4_unicode_ci NOT NULL,
  `message` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `course_scope` enum('introduction','graduation_project','both') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'both',
  `related_project_id` int DEFAULT NULL,
  `is_read` tinyint(1) NOT NULL DEFAULT '0',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`notification_id`),
  KEY `sender_id` (`sender_id`),
  KEY `idx_notif_recipient` (`recipient_id`,`is_read`),
  KEY `idx_notif_project` (`related_project_id`),
  CONSTRAINT `notifications_ibfk_1` FOREIGN KEY (`recipient_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE,
  CONSTRAINT `notifications_ibfk_2` FOREIGN KEY (`sender_id`) REFERENCES `users` (`user_id`) ON DELETE SET NULL,
  CONSTRAINT `notifications_ibfk_3` FOREIGN KEY (`related_project_id`) REFERENCES `projects` (`project_id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=48 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `notifications`
--

LOCK TABLES `notifications` WRITE;
/*!40000 ALTER TABLE `notifications` DISABLE KEYS */;
INSERT INTO `notifications` VALUES (1,2,4,'project_reviewed','Dr. Radi Jarrar completed evaluations','Dr. Radi Jarrar completed 3 project evaluations — avg score: 89.3.','both',NULL,0,'2026-05-20 13:03:29'),(2,2,NULL,'deadline_reminder','7 projects awaiting your decision','7 projects are pending coordinator review — some exceeded 48 hours.','both',NULL,1,'2026-05-20 13:03:29'),(10,8,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-20 13:45:01'),(11,9,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-20 13:45:01'),(12,10,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-20 13:45:01'),(13,8,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-20 13:45:01'),(14,9,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-20 13:45:01'),(15,10,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-20 13:45:01'),(16,8,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-20 13:45:01'),(17,9,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-20 13:45:01'),(18,10,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-20 13:45:01'),(19,11,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',2,0,'2026-05-20 13:45:01'),(20,8,3,'feedback_received','Your project has been reviewed','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-20 13:45:01'),(21,8,2,'committee_assigned','Committee discussion scheduled','Your project discussion is scheduled for February 20 at 10:00 AM.','both',1,0,'2026-05-20 13:45:01'),(22,8,NULL,'deadline_reminder','Reminder: Upload source code','Please upload the source code files before February 15.','both',1,0,'2026-05-20 13:45:01'),(23,3,8,'file_uploaded','Rahaf Badwan uploaded updated files','A new version of the final report has been uploaded — APMS project.','both',1,0,'2026-05-20 13:45:01'),(24,3,2,'committee_assigned','New committee membership assigned','You have been assigned as a member of a new evaluation committee.','both',1,0,'2026-05-20 13:45:01'),(25,3,NULL,'urgent_alert','Karim Odeh — urgent follow-up needed','Karim Odeh has not uploaded any files for two weeks.','both',3,0,'2026-05-20 13:45:01'),(26,2,NULL,'file_uploaded','New project pending your review','Electronic Student Records Management System — Salma Al-Khatib.','both',2,0,'2026-05-20 13:45:01'),(27,2,4,'project_reviewed','Dr. Radi Jarrar completed evaluations','Dr. Radi Jarrar completed 3 project evaluations — avg score: 89.3.','both',NULL,0,'2026-05-20 13:45:01'),(28,2,NULL,'deadline_reminder','7 projects awaiting your decision','7 projects are pending coordinator review — some exceeded 48 hours.','both',NULL,1,'2026-05-20 13:45:01'),(29,8,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-20 13:57:21'),(30,9,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-20 13:57:21'),(31,10,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-20 13:57:21'),(32,8,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-20 13:57:21'),(33,9,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-20 13:57:21'),(34,10,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-20 13:57:21'),(35,8,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-20 13:57:21'),(36,9,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-20 13:57:21'),(37,10,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-20 13:57:21'),(38,11,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',2,0,'2026-05-20 13:57:21'),(39,8,3,'feedback_received','Your project has been reviewed','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-20 13:57:21'),(40,8,2,'committee_assigned','Committee discussion scheduled','Your project discussion is scheduled for February 20 at 10:00 AM.','both',1,0,'2026-05-20 13:57:21'),(41,8,NULL,'deadline_reminder','Reminder: Upload source code','Please upload the source code files before February 15.','both',1,0,'2026-05-20 13:57:21'),(42,3,8,'file_uploaded','Rahaf Badwan uploaded updated files','A new version of the final report has been uploaded — APMS project.','both',1,0,'2026-05-20 13:57:21'),(43,3,2,'committee_assigned','New committee membership assigned','You have been assigned as a member of a new evaluation committee.','both',1,0,'2026-05-20 13:57:21'),(44,3,NULL,'urgent_alert','Karim Odeh — urgent follow-up needed','Karim Odeh has not uploaded any files for two weeks.','both',3,0,'2026-05-20 13:57:21'),(45,2,NULL,'file_uploaded','New project pending your review','Electronic Student Records Management System — Salma Al-Khatib.','both',2,0,'2026-05-20 13:57:21'),(46,2,4,'project_reviewed','Dr. Radi Jarrar completed evaluations','Dr. Radi Jarrar completed 3 project evaluations — avg score: 89.3.','both',NULL,0,'2026-05-20 13:57:21'),(47,2,NULL,'deadline_reminder','7 projects awaiting your decision','7 projects are pending coordinator review — some exceeded 48 hours.','both',NULL,1,'2026-05-20 13:57:21');
/*!40000 ALTER TABLE `notifications` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `password_reset_tokens`
--

DROP TABLE IF EXISTS `password_reset_tokens`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `password_reset_tokens` (
  `token_id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `token` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `expires_at` datetime NOT NULL,
  `used` tinyint(1) NOT NULL DEFAULT '0',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`token_id`),
  UNIQUE KEY `token` (`token`),
  KEY `user_id` (`user_id`),
  KEY `idx_token` (`token`),
  KEY `idx_expires` (`expires_at`),
  CONSTRAINT `password_reset_tokens_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `password_reset_tokens`
--

LOCK TABLES `password_reset_tokens` WRITE;
/*!40000 ALTER TABLE `password_reset_tokens` DISABLE KEYS */;
/*!40000 ALTER TABLE `password_reset_tokens` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `project_evaluation_windows`
--

DROP TABLE IF EXISTS `project_evaluation_windows`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `project_evaluation_windows` (
  `window_id` int NOT NULL AUTO_INCREMENT,
  `project_id` int NOT NULL,
  `course_scope` enum('introduction','graduation_project') NOT NULL,
  `is_open` tinyint(1) NOT NULL DEFAULT '0',
  `opened_by` int DEFAULT NULL,
  `opened_at` datetime DEFAULT NULL,
  `closed_at` datetime DEFAULT NULL,
  `due_at` datetime DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`window_id`),
  UNIQUE KEY `uq_eval_window_project_course` (`project_id`,`course_scope`),
  KEY `opened_by` (`opened_by`),
  CONSTRAINT `project_evaluation_windows_ibfk_1` FOREIGN KEY (`project_id`) REFERENCES `projects` (`project_id`) ON DELETE CASCADE,
  CONSTRAINT `project_evaluation_windows_ibfk_2` FOREIGN KEY (`opened_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `project_evaluation_windows`
--

LOCK TABLES `project_evaluation_windows` WRITE;
/*!40000 ALTER TABLE `project_evaluation_windows` DISABLE KEYS */;
/*!40000 ALTER TABLE `project_evaluation_windows` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `project_files`
--

DROP TABLE IF EXISTS `project_files`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `project_files` (
  `file_id` int NOT NULL AUTO_INCREMENT,
  `project_id` int NOT NULL,
  `file_type` enum('final_report','source_code','presentation','other') COLLATE utf8mb4_unicode_ci NOT NULL,
  `file_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `file_path` varchar(600) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `file_data` longblob COMMENT 'Binary file content stored in DB',
  `file_mime` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'MIME type of the uploaded file',
  `file_size_mb` decimal(7,2) DEFAULT NULL,
  `upload_status` enum('not_uploaded','uploaded','required') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'not_uploaded',
  `uploaded_by` int DEFAULT NULL COMMENT 'student user_id',
  `uploaded_at` timestamp NULL DEFAULT NULL,
  `version` tinyint NOT NULL DEFAULT '1',
  PRIMARY KEY (`file_id`),
  UNIQUE KEY `uq_project_file_type` (`project_id`,`file_type`),
  KEY `uploaded_by` (`uploaded_by`),
  KEY `idx_files_project` (`project_id`,`file_type`),
  CONSTRAINT `project_files_ibfk_1` FOREIGN KEY (`project_id`) REFERENCES `projects` (`project_id`) ON DELETE CASCADE,
  CONSTRAINT `project_files_ibfk_2` FOREIGN KEY (`uploaded_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=89 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `project_files`
--

LOCK TABLES `project_files` WRITE;
/*!40000 ALTER TABLE `project_files` DISABLE KEYS */;
INSERT INTO `project_files` VALUES (1,12,'final_report','smart_invoice.pdf','archived_reports/smart_invoice.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:33',1),(2,13,'final_report','kitchen_station.pdf','archived_reports/kitchen_station.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:33',1),(3,14,'final_report','dreamsjob.pdf','archived_reports/dreamsjob.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:33',1),(4,15,'final_report','yallarehla.pdf','archived_reports/yallarehla.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:33',1),(5,16,'final_report','studenthub.pdf','archived_reports/studenthub.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:33',1),(6,17,'final_report','wasselha.pdf','archived_reports/wasselha.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:33',1),(7,18,'final_report','home_sweet_home.pdf','archived_reports/home_sweet_home.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(8,19,'final_report','bzu_insurance.pdf','archived_reports/bzu_insurance.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(9,20,'final_report','sal7ly.pdf','archived_reports/sal7ly.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(10,21,'final_report','monitoring_world_news.pdf','archived_reports/monitoring_world_news.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(11,22,'final_report','anti_cancer_peptide.pdf','archived_reports/anti_cancer_peptide.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(12,23,'final_report','fitscoop.pdf','archived_reports/fitscoop.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(13,24,'final_report','wedding_planning.pdf','archived_reports/wedding_planning.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(14,25,'final_report','pharmaapp.pdf','archived_reports/pharmaapp.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(15,26,'final_report','student_digital_guide.pdf','archived_reports/student_digital_guide.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(16,27,'final_report','palestine_charity.pdf','archived_reports/palestine_charity.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(17,28,'final_report','gamified_trip_planner.pdf','archived_reports/gamified_trip_planner.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(18,29,'final_report','techspotter.pdf','archived_reports/techspotter.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(19,30,'final_report','multi_env_videogame.pdf','archived_reports/multi_env_videogame.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(20,31,'final_report','bzu_library_chatbot.pdf','archived_reports/bzu_library_chatbot.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(21,32,'final_report','policy_peek.pdf','archived_reports/policy_peek.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(22,33,'final_report','lifeactive.pdf','archived_reports/lifeactive.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(23,34,'final_report','tronix.pdf','archived_reports/tronix.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(24,35,'final_report','smart_school_portal.pdf','archived_reports/smart_school_portal.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(25,36,'final_report','gohelp.pdf','archived_reports/gohelp.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(26,37,'final_report','khatclarifier.pdf','archived_reports/khatclarifier.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(27,38,'final_report','convoconvert.pdf','archived_reports/convoconvert.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(28,39,'final_report','wasselni.pdf','archived_reports/wasselni.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(29,40,'final_report','ackerra.pdf','archived_reports/ackerra.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(30,41,'final_report','darak.pdf','archived_reports/darak.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(31,42,'final_report','flora_palestine.pdf','archived_reports/flora_palestine.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(32,43,'final_report','max_scheduling.pdf','archived_reports/max_scheduling.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(33,44,'final_report','paywithpalkoin.pdf','archived_reports/paywithpalkoin.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(34,45,'final_report','nomad.pdf','archived_reports/nomad.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(35,46,'final_report','carpal.pdf','archived_reports/carpal.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(36,47,'final_report','evoting_blockchain.pdf','archived_reports/evoting_blockchain.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(37,48,'final_report','nossrah.pdf','archived_reports/nossrah.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(38,49,'final_report','wanderlust_palestine.pdf','archived_reports/wanderlust_palestine.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(39,50,'final_report','medica_app.pdf','archived_reports/medica_app.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(40,51,'final_report','bzu_note_share.pdf','archived_reports/bzu_note_share.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(41,52,'final_report','plestia_events.pdf','archived_reports/plestia_events.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(42,53,'final_report','baby_voice_id.pdf','archived_reports/baby_voice_id.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(43,54,'final_report','traffic_light_optimizer.pdf','archived_reports/traffic_light_optimizer.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(44,55,'final_report','campus_connect.pdf','archived_reports/campus_connect.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:03:34',1),(45,71,'final_report','smart_invoice.pdf','archived_reports/smart_invoice.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(46,72,'final_report','kitchen_station.pdf','archived_reports/kitchen_station.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(47,73,'final_report','dreamsjob.pdf','archived_reports/dreamsjob.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(48,74,'final_report','yallarehla.pdf','archived_reports/yallarehla.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(49,75,'final_report','studenthub.pdf','archived_reports/studenthub.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(50,76,'final_report','wasselha.pdf','archived_reports/wasselha.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(51,77,'final_report','home_sweet_home.pdf','archived_reports/home_sweet_home.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(52,78,'final_report','bzu_insurance.pdf','archived_reports/bzu_insurance.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(53,79,'final_report','sal7ly.pdf','archived_reports/sal7ly.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(54,80,'final_report','monitoring_world_news.pdf','archived_reports/monitoring_world_news.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(55,81,'final_report','anti_cancer_peptide.pdf','archived_reports/anti_cancer_peptide.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(56,82,'final_report','fitscoop.pdf','archived_reports/fitscoop.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(57,83,'final_report','wedding_planning.pdf','archived_reports/wedding_planning.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(58,84,'final_report','pharmaapp.pdf','archived_reports/pharmaapp.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(59,85,'final_report','student_digital_guide.pdf','archived_reports/student_digital_guide.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(60,86,'final_report','palestine_charity.pdf','archived_reports/palestine_charity.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(61,87,'final_report','gamified_trip_planner.pdf','archived_reports/gamified_trip_planner.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(62,88,'final_report','techspotter.pdf','archived_reports/techspotter.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(63,89,'final_report','multi_env_videogame.pdf','archived_reports/multi_env_videogame.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(64,90,'final_report','bzu_library_chatbot.pdf','archived_reports/bzu_library_chatbot.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(65,91,'final_report','policy_peek.pdf','archived_reports/policy_peek.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(66,92,'final_report','lifeactive.pdf','archived_reports/lifeactive.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(67,93,'final_report','tronix.pdf','archived_reports/tronix.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(68,94,'final_report','smart_school_portal.pdf','archived_reports/smart_school_portal.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(69,95,'final_report','gohelp.pdf','archived_reports/gohelp.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(70,96,'final_report','khatclarifier.pdf','archived_reports/khatclarifier.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(71,97,'final_report','convoconvert.pdf','archived_reports/convoconvert.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(72,98,'final_report','wasselni.pdf','archived_reports/wasselni.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(73,99,'final_report','ackerra.pdf','archived_reports/ackerra.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(74,100,'final_report','darak.pdf','archived_reports/darak.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(75,101,'final_report','flora_palestine.pdf','archived_reports/flora_palestine.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(76,102,'final_report','max_scheduling.pdf','archived_reports/max_scheduling.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(77,103,'final_report','paywithpalkoin.pdf','archived_reports/paywithpalkoin.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(78,104,'final_report','nomad.pdf','archived_reports/nomad.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(79,105,'final_report','carpal.pdf','archived_reports/carpal.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(80,106,'final_report','evoting_blockchain.pdf','archived_reports/evoting_blockchain.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(81,107,'final_report','nossrah.pdf','archived_reports/nossrah.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(82,108,'final_report','wanderlust_palestine.pdf','archived_reports/wanderlust_palestine.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(83,109,'final_report','medica_app.pdf','archived_reports/medica_app.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(84,110,'final_report','bzu_note_share.pdf','archived_reports/bzu_note_share.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(85,111,'final_report','plestia_events.pdf','archived_reports/plestia_events.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(86,112,'final_report','baby_voice_id.pdf','archived_reports/baby_voice_id.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(87,113,'final_report','traffic_light_optimizer.pdf','archived_reports/traffic_light_optimizer.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1),(88,114,'final_report','campus_connect.pdf','archived_reports/campus_connect.pdf',NULL,NULL,NULL,'uploaded',NULL,'2026-05-20 13:45:27',1);
/*!40000 ALTER TABLE `project_files` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `project_final_evaluation_results`
--

DROP TABLE IF EXISTS `project_final_evaluation_results`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `project_final_evaluation_results` (
  `result_id` int NOT NULL AUTO_INCREMENT,
  `project_id` int NOT NULL,
  `course_scope` enum('introduction','graduation_project') NOT NULL,
  `report_score` decimal(6,2) DEFAULT NULL,
  `supervisor_score` decimal(6,2) DEFAULT NULL,
  `coordinator_score` decimal(6,2) DEFAULT NULL,
  `discussion_score` decimal(6,2) DEFAULT NULL,
  `committee_score` decimal(6,2) DEFAULT NULL,
  `final_score` decimal(6,2) DEFAULT NULL,
  `decision` enum('pending','accepted','rejected','archived') NOT NULL DEFAULT 'pending',
  `notes` text,
  `published_by` int DEFAULT NULL,
  `published_at` datetime DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`result_id`),
  UNIQUE KEY `uq_eval_result_project_course` (`project_id`,`course_scope`),
  KEY `published_by` (`published_by`),
  CONSTRAINT `project_final_evaluation_results_ibfk_1` FOREIGN KEY (`project_id`) REFERENCES `projects` (`project_id`) ON DELETE CASCADE,
  CONSTRAINT `project_final_evaluation_results_ibfk_2` FOREIGN KEY (`published_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `project_final_evaluation_results`
--

LOCK TABLES `project_final_evaluation_results` WRITE;
/*!40000 ALTER TABLE `project_final_evaluation_results` DISABLE KEYS */;
/*!40000 ALTER TABLE `project_final_evaluation_results` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `project_grade_entries`
--

DROP TABLE IF EXISTS `project_grade_entries`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `project_grade_entries` (
  `grade_id` int NOT NULL AUTO_INCREMENT,
  `project_id` int NOT NULL,
  `course_scope` enum('introduction','graduation_project') NOT NULL,
  `component` enum('intro_report_reader','intro_coordinator','intro_supervisor','intro_discussion_member','grad_report_reader','grad_supervisor','grad_committee_member') NOT NULL,
  `evaluator_user_id` int NOT NULL,
  `evaluator_faculty_id` int DEFAULT NULL,
  `mark` decimal(6,2) DEFAULT NULL,
  `max_mark` decimal(6,2) NOT NULL,
  `notes` text,
  `is_submitted` tinyint(1) NOT NULL DEFAULT '0',
  `submitted_at` datetime DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`grade_id`),
  UNIQUE KEY `uq_grade_once` (`project_id`,`course_scope`,`component`,`evaluator_user_id`),
  KEY `idx_grade_project_course` (`project_id`,`course_scope`),
  KEY `idx_grade_evaluator` (`evaluator_user_id`),
  KEY `evaluator_faculty_id` (`evaluator_faculty_id`),
  CONSTRAINT `project_grade_entries_ibfk_1` FOREIGN KEY (`project_id`) REFERENCES `projects` (`project_id`) ON DELETE CASCADE,
  CONSTRAINT `project_grade_entries_ibfk_2` FOREIGN KEY (`evaluator_user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE,
  CONSTRAINT `project_grade_entries_ibfk_3` FOREIGN KEY (`evaluator_faculty_id`) REFERENCES `faculty` (`faculty_id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `project_grade_entries`
--

LOCK TABLES `project_grade_entries` WRITE;
/*!40000 ALTER TABLE `project_grade_entries` DISABLE KEYS */;
/*!40000 ALTER TABLE `project_grade_entries` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `project_lifecycle`
--

DROP TABLE IF EXISTS `project_lifecycle`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `project_lifecycle` (
  `lifecycle_id` int NOT NULL AUTO_INCREMENT,
  `project_id` int NOT NULL,
  `stage` enum('registration','file_submission','initial_review','supervisor_review','committee_evaluation','final_result','archiving') COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` enum('pending','in_progress','completed','skipped') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `scheduled_date` date DEFAULT NULL,
  `completed_date` date DEFAULT NULL,
  `notes` text COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`lifecycle_id`),
  UNIQUE KEY `uq_project_stage` (`project_id`,`stage`),
  KEY `idx_lifecycle_project` (`project_id`,`stage`),
  CONSTRAINT `project_lifecycle_ibfk_1` FOREIGN KEY (`project_id`) REFERENCES `projects` (`project_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=40 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `project_lifecycle`
--

LOCK TABLES `project_lifecycle` WRITE;
/*!40000 ALTER TABLE `project_lifecycle` DISABLE KEYS */;
INSERT INTO `project_lifecycle` VALUES (14,1,'registration','completed','2026-01-25','2026-01-25','Project registered successfully'),(15,1,'file_submission','completed','2026-02-01','2026-02-01','Report and source code uploaded — slides still required'),(16,1,'initial_review','in_progress','2026-02-03',NULL,'Supervisor Dr. Naima is reviewing the final report; feedback expected within 48 hours'),(17,1,'supervisor_review','pending',NULL,NULL,NULL),(18,1,'committee_evaluation','pending','2026-02-20',NULL,NULL),(19,1,'final_result','pending','2026-02-28',NULL,NULL),(20,1,'archiving','pending',NULL,NULL,NULL),(21,4,'registration','completed','2025-01-15','2025-01-15',NULL),(22,4,'file_submission','completed','2025-02-01','2025-02-01',NULL),(23,4,'initial_review','completed','2025-02-05','2025-02-05',NULL),(24,4,'committee_evaluation','completed','2025-02-21','2025-02-21',NULL),(25,4,'final_result','completed','2025-02-28','2025-02-28',NULL),(26,4,'archiving','completed','2025-03-01','2025-03-01',NULL);
/*!40000 ALTER TABLE `project_lifecycle` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `project_members`
--

DROP TABLE IF EXISTS `project_members`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `project_members` (
  `member_id` int NOT NULL AUTO_INCREMENT,
  `project_id` int NOT NULL,
  `student_id` int NOT NULL,
  `is_primary_contact` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'Primary contact for the project',
  `joined_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`member_id`),
  UNIQUE KEY `uq_project_student` (`project_id`,`student_id`),
  KEY `idx_members_project` (`project_id`),
  KEY `idx_members_student` (`student_id`),
  CONSTRAINT `project_members_ibfk_1` FOREIGN KEY (`project_id`) REFERENCES `projects` (`project_id`) ON DELETE CASCADE,
  CONSTRAINT `project_members_ibfk_2` FOREIGN KEY (`student_id`) REFERENCES `students` (`student_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=71 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `project_members`
--

LOCK TABLES `project_members` WRITE;
/*!40000 ALTER TABLE `project_members` DISABLE KEYS */;
INSERT INTO `project_members` VALUES (19,4,11,1,'2026-05-20 13:03:32'),(20,4,12,0,'2026-05-20 13:03:32'),(21,5,13,1,'2026-05-20 13:03:32'),(22,5,14,0,'2026-05-20 13:03:32'),(23,6,15,1,'2026-05-20 13:03:32'),(24,6,16,0,'2026-05-20 13:03:32'),(25,7,17,1,'2026-05-20 13:03:32'),(26,7,18,0,'2026-05-20 13:03:32'),(27,8,19,1,'2026-05-20 13:03:32'),(28,8,20,0,'2026-05-20 13:03:32'),(29,9,21,1,'2026-05-20 13:03:32'),(30,9,22,0,'2026-05-20 13:03:32'),(31,10,23,1,'2026-05-20 13:03:32'),(32,10,24,0,'2026-05-20 13:03:32'),(33,11,25,1,'2026-05-20 13:03:32'),(34,11,26,0,'2026-05-20 13:03:32'),(35,1,2,0,'2026-05-20 13:45:01'),(36,1,1,1,'2026-05-20 13:45:01'),(37,1,3,0,'2026-05-20 13:45:01'),(38,2,4,1,'2026-05-20 13:45:01'),(39,3,5,1,'2026-05-20 13:45:01'),(40,4,6,1,'2026-05-20 13:45:01'),(41,5,7,1,'2026-05-20 13:45:01'),(42,6,8,1,'2026-05-20 13:45:01'),(43,9,8,0,'2026-05-20 13:45:01'),(44,10,9,1,'2026-05-20 13:45:02'),(45,10,10,0,'2026-05-20 13:45:02'),(46,11,4,1,'2026-05-20 13:45:02'),(47,11,5,0,'2026-05-20 13:45:02'),(48,12,6,1,'2026-05-20 13:45:02'),(49,12,7,0,'2026-05-20 13:45:02'),(50,12,8,0,'2026-05-20 13:45:02');
/*!40000 ALTER TABLE `project_members` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `project_progress`
--

DROP TABLE IF EXISTS `project_progress`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `project_progress` (
  `progress_id` int NOT NULL AUTO_INCREMENT,
  `project_id` int NOT NULL,
  `component` enum('final_report','source_code','presentation','overall') COLLATE utf8mb4_unicode_ci NOT NULL,
  `percentage` tinyint NOT NULL DEFAULT '0',
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `updated_by` int DEFAULT NULL,
  PRIMARY KEY (`progress_id`),
  UNIQUE KEY `uq_project_component` (`project_id`,`component`),
  KEY `updated_by` (`updated_by`),
  CONSTRAINT `project_progress_ibfk_1` FOREIGN KEY (`project_id`) REFERENCES `projects` (`project_id`) ON DELETE CASCADE,
  CONSTRAINT `project_progress_ibfk_2` FOREIGN KEY (`updated_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL,
  CONSTRAINT `project_progress_chk_1` CHECK ((`percentage` between 0 and 100))
) ENGINE=InnoDB AUTO_INCREMENT=22 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `project_progress`
--

LOCK TABLES `project_progress` WRITE;
/*!40000 ALTER TABLE `project_progress` DISABLE KEYS */;
INSERT INTO `project_progress` VALUES (8,1,'final_report',85,'2026-05-20 13:45:01',3),(9,1,'source_code',70,'2026-05-20 13:45:01',3),(10,1,'presentation',60,'2026-05-20 13:45:01',3),(11,1,'overall',78,'2026-05-20 13:45:01',3),(12,3,'final_report',55,'2026-05-20 13:45:01',5),(13,3,'source_code',48,'2026-05-20 13:45:01',5),(14,3,'overall',31,'2026-05-20 13:45:01',5);
/*!40000 ALTER TABLE `project_progress` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `project_report_readers`
--

DROP TABLE IF EXISTS `project_report_readers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `project_report_readers` (
  `id` int NOT NULL AUTO_INCREMENT,
  `project_id` int NOT NULL,
  `faculty_id` int NOT NULL,
  `reader_order` tinyint NOT NULL,
  `assigned_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_project_reader_order` (`project_id`,`reader_order`),
  UNIQUE KEY `uq_project_reader_faculty` (`project_id`,`faculty_id`),
  KEY `faculty_id` (`faculty_id`),
  CONSTRAINT `project_report_readers_ibfk_1` FOREIGN KEY (`project_id`) REFERENCES `projects` (`project_id`) ON DELETE CASCADE,
  CONSTRAINT `project_report_readers_ibfk_2` FOREIGN KEY (`faculty_id`) REFERENCES `faculty` (`faculty_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `project_report_readers`
--

LOCK TABLES `project_report_readers` WRITE;
/*!40000 ALTER TABLE `project_report_readers` DISABLE KEYS */;
/*!40000 ALTER TABLE `project_report_readers` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `projects`
--

DROP TABLE IF EXISTS `projects`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `projects` (
  `project_id` int NOT NULL AUTO_INCREMENT,
  `group_name` varchar(120) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `title` varchar(300) COLLATE utf8mb4_unicode_ci NOT NULL,
  `title_en` varchar(300) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `abstract` text COLLATE utf8mb4_unicode_ci,
  `keywords` varchar(600) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `project_type` set('web','mobile','ai','software_engineering','security','databases','other') COLLATE utf8mb4_unicode_ci NOT NULL,
  `semester_id` int NOT NULL,
  `supervisor_id` int DEFAULT NULL,
  `preferred_supervisor_1` int DEFAULT NULL,
  `preferred_supervisor_2` int DEFAULT NULL,
  `preferred_supervisor_3` int DEFAULT NULL,
  `status` enum('draft','submitted','under_review','needs_revision','committee_evaluation','accepted','rejected','archived') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'draft',
  `submission_date` date DEFAULT NULL,
  `coordinator_notes` text COLLATE utf8mb4_unicode_ci,
  `rejection_reason` text COLLATE utf8mb4_unicode_ci,
  `final_score` decimal(5,2) DEFAULT NULL COMMENT 'Final score out of 100',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`project_id`),
  KEY `idx_projects_semester` (`semester_id`),
  KEY `idx_projects_supervisor` (`supervisor_id`),
  KEY `idx_projects_status` (`status`),
  KEY `fk_projects_pref_sup_1` (`preferred_supervisor_1`),
  KEY `fk_projects_pref_sup_2` (`preferred_supervisor_2`),
  KEY `fk_projects_pref_sup_3` (`preferred_supervisor_3`),
  CONSTRAINT `fk_projects_pref_sup_1` FOREIGN KEY (`preferred_supervisor_1`) REFERENCES `faculty` (`faculty_id`) ON DELETE SET NULL,
  CONSTRAINT `fk_projects_pref_sup_2` FOREIGN KEY (`preferred_supervisor_2`) REFERENCES `faculty` (`faculty_id`) ON DELETE SET NULL,
  CONSTRAINT `fk_projects_pref_sup_3` FOREIGN KEY (`preferred_supervisor_3`) REFERENCES `faculty` (`faculty_id`) ON DELETE SET NULL,
  CONSTRAINT `projects_ibfk_1` FOREIGN KEY (`semester_id`) REFERENCES `semesters` (`semester_id`),
  CONSTRAINT `projects_ibfk_2` FOREIGN KEY (`supervisor_id`) REFERENCES `faculty` (`faculty_id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=115 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `projects`
--

LOCK TABLES `projects` WRITE;
/*!40000 ALTER TABLE `projects` DISABLE KEYS */;
INSERT INTO `projects` VALUES (1,NULL,'Advanced AI Decision System',NULL,NULL,NULL,'ai',5,4,NULL,NULL,NULL,'draft','2026-05-20',NULL,NULL,NULL,'2026-05-20 13:03:29','2026-05-20 13:03:35'),(2,NULL,'Enterprise Web Platform',NULL,NULL,NULL,'web',5,5,NULL,NULL,NULL,'draft','2026-05-20',NULL,NULL,NULL,'2026-05-20 13:03:29','2026-05-20 13:03:35'),(3,NULL,'Cyber Security Audit Platform',NULL,NULL,NULL,'security',5,7,NULL,NULL,NULL,'draft','2026-05-20',NULL,NULL,NULL,'2026-05-20 13:03:29','2026-05-20 13:03:35'),(4,NULL,'Smart Clinic Management Platform',NULL,NULL,NULL,'web',5,5,NULL,NULL,NULL,'submitted','2026-05-20',NULL,NULL,NULL,'2026-05-20 13:03:32','2026-05-20 13:03:32'),(5,NULL,'AI Resume Screening System',NULL,NULL,NULL,'ai',5,4,NULL,NULL,NULL,'submitted','2026-05-20',NULL,NULL,NULL,'2026-05-20 13:03:32','2026-05-20 13:03:32'),(6,NULL,'Secure Campus Access Control',NULL,NULL,NULL,'security',5,7,NULL,NULL,NULL,'submitted','2026-05-20',NULL,NULL,NULL,'2026-05-20 13:03:32','2026-05-20 13:03:32'),(7,NULL,'Mobile Pharmacy Assistant',NULL,NULL,NULL,'mobile',5,5,NULL,NULL,NULL,'submitted','2026-05-20',NULL,NULL,NULL,'2026-05-20 13:03:32','2026-05-20 13:03:32'),(8,NULL,'Intelligent Library Recommender',NULL,NULL,NULL,'ai',5,4,NULL,NULL,NULL,'submitted','2026-05-20',NULL,NULL,NULL,'2026-05-20 13:03:32','2026-05-20 13:03:32'),(9,NULL,'Cloud Attendance Tracker',NULL,NULL,NULL,'web',5,3,NULL,NULL,NULL,'submitted','2026-05-20',NULL,NULL,NULL,'2026-05-20 13:03:32','2026-05-20 13:03:32'),(10,NULL,'Database Performance Analyzer',NULL,NULL,NULL,'databases',5,6,NULL,NULL,NULL,'submitted','2026-05-20',NULL,NULL,NULL,'2026-05-20 13:03:32','2026-05-20 13:03:32'),(11,NULL,'Smart Graduation Project Marketplace',NULL,NULL,NULL,'web',5,3,NULL,NULL,NULL,'submitted','2026-05-20',NULL,NULL,NULL,'2026-05-20 13:03:32','2026-05-20 13:03:32'),(12,NULL,'Smart Invoice',NULL,NULL,NULL,'ai',2,3,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,82.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(13,NULL,'Kitchen Station Management System',NULL,NULL,NULL,'web',2,4,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,79.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(14,NULL,'DreamsJob Recruitment Platform',NULL,NULL,NULL,'web',2,5,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,85.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(15,NULL,'YallaRehla Travel App',NULL,NULL,NULL,'mobile',2,6,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,88.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(16,NULL,'StudentHub',NULL,NULL,NULL,'web',2,7,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,76.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(17,NULL,'Wasselha Delivery System',NULL,NULL,NULL,'mobile',2,3,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,83.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(18,NULL,'Home Sweet Home Real Estate',NULL,NULL,NULL,'web',2,4,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,80.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(19,NULL,'Birzeit University Insurance System',NULL,NULL,NULL,'web',3,5,NULL,NULL,NULL,'draft','2024-02-01',NULL,NULL,91.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(20,NULL,'Sal7ly Maintenance App',NULL,NULL,NULL,'mobile',3,6,NULL,NULL,NULL,'draft','2024-02-01',NULL,NULL,78.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(21,NULL,'Monitoring World News System',NULL,NULL,NULL,'web',3,7,NULL,NULL,NULL,'draft','2024-02-01',NULL,NULL,74.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(22,NULL,'Prediction of Anti-Cancer Peptide ACP-XG',NULL,NULL,NULL,'ai',2,3,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,94.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(23,NULL,'FitScoop Fitness Platform',NULL,NULL,NULL,'mobile',2,4,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,81.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(24,NULL,'Wedding Planning System',NULL,NULL,NULL,'web',2,5,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,77.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(25,NULL,'PharmaApp Pharmacy Management',NULL,NULL,NULL,'mobile',2,6,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,86.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(26,NULL,'Student Digital Guide',NULL,NULL,NULL,'web',2,7,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,80.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(27,NULL,'Palestine Charity Platform',NULL,NULL,NULL,'web',2,3,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,75.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(28,NULL,'Gamified Trip Planner App',NULL,NULL,NULL,'mobile',2,4,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,89.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(29,NULL,'TechSpotter Tech News Platform',NULL,NULL,NULL,'web',2,5,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,78.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(30,NULL,'Multi-Environment Video Game',NULL,NULL,NULL,'other',2,6,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,83.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(31,NULL,'Birzeit Library Chatbot',NULL,NULL,NULL,'ai',2,7,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,92.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(32,NULL,'Policy Peek Policy Analyzer',NULL,NULL,NULL,'ai',2,3,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,87.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(33,NULL,'LifeActive Health Tracker',NULL,NULL,NULL,'mobile',2,4,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,84.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(34,NULL,'Tronix Electronics Web Application',NULL,NULL,NULL,'web',2,5,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,79.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(35,NULL,'Smart School Portal',NULL,NULL,NULL,'web',2,6,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,88.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(36,NULL,'GoHelp Volunteer Platform',NULL,NULL,NULL,'web',2,7,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,76.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(37,NULL,'KhatClarifier AI Writing Tool',NULL,NULL,NULL,'ai',2,3,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,90.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(38,NULL,'ConvoConvert Communication Tool',NULL,NULL,NULL,'ai',2,4,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,85.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(39,NULL,'Wasselni Transportation App',NULL,NULL,NULL,'mobile',2,5,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,82.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(40,NULL,'Ackerra Fitness Platform',NULL,NULL,NULL,'mobile',2,6,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,87.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(41,NULL,'Darak Real Estate Marketplace',NULL,NULL,NULL,'web',2,7,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,83.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(42,NULL,'Flora Palestine Plant Guide',NULL,NULL,NULL,'mobile',2,3,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,81.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(43,NULL,'Max Scheduling System',NULL,NULL,NULL,'web',2,4,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,77.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(44,NULL,'PayWithPalKoin Payment System',NULL,NULL,NULL,'web',2,5,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,86.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(45,NULL,'Nomad Travel Companion App',NULL,NULL,NULL,'mobile',2,6,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,84.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(46,NULL,'CarPal Car Sharing App',NULL,NULL,NULL,'mobile',2,7,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,88.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(47,NULL,'E-Voting System Using Blockchain',NULL,NULL,NULL,'security',3,3,NULL,NULL,NULL,'draft','2024-02-01',NULL,NULL,93.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(48,NULL,'Nossrah Arabic Learning App',NULL,NULL,NULL,'mobile',3,4,NULL,NULL,NULL,'draft','2024-02-01',NULL,NULL,80.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(49,NULL,'Wanderlust in Palestine Travel App',NULL,NULL,NULL,'web',3,5,NULL,NULL,NULL,'draft','2024-02-01',NULL,NULL,85.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(50,NULL,'Medica Healthcare App',NULL,NULL,NULL,'mobile',3,6,NULL,NULL,NULL,'draft','2024-02-01',NULL,NULL,82.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(51,NULL,'BZU Note Share App',NULL,NULL,NULL,'mobile',3,7,NULL,NULL,NULL,'draft','2024-02-01',NULL,NULL,79.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(52,NULL,'Plestia Events Platform',NULL,NULL,NULL,'web',3,3,NULL,NULL,NULL,'draft','2024-02-01',NULL,NULL,83.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(53,NULL,'Baby Voice Identification App',NULL,NULL,NULL,'ai',3,4,NULL,NULL,NULL,'draft','2024-02-01',NULL,NULL,88.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(54,NULL,'Traffic Light Synchronization Optimizer',NULL,NULL,NULL,'ai',3,5,NULL,NULL,NULL,'draft','2024-02-01',NULL,NULL,91.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(55,NULL,'CampusConnect University Network',NULL,NULL,NULL,'web',3,6,NULL,NULL,NULL,'draft','2024-02-01',NULL,NULL,86.00,'2026-05-20 13:03:33','2026-05-20 13:03:35'),(56,NULL,'Committee Demo AI Project 01',NULL,NULL,NULL,'ai',5,18,NULL,NULL,NULL,'draft','2026-05-20',NULL,NULL,NULL,'2026-05-20 13:03:34','2026-05-20 13:03:35'),(57,NULL,'Committee Demo AI Project 02',NULL,NULL,NULL,'ai',5,18,NULL,NULL,NULL,'draft','2026-05-20',NULL,NULL,NULL,'2026-05-20 13:03:34','2026-05-20 13:03:35'),(58,NULL,'Committee Demo Web Project 01',NULL,NULL,NULL,'web',5,2,NULL,NULL,NULL,'draft','2026-05-20',NULL,NULL,NULL,'2026-05-20 13:03:34','2026-05-20 13:03:35'),(59,NULL,'Committee Demo Web Project 02',NULL,NULL,NULL,'web',5,2,NULL,NULL,NULL,'draft','2026-05-20',NULL,NULL,NULL,'2026-05-20 13:03:34','2026-05-20 13:03:35'),(60,NULL,'Committee Demo SE Project 01',NULL,NULL,NULL,'software_engineering',5,1,NULL,NULL,NULL,'draft','2026-05-20',NULL,NULL,NULL,'2026-05-20 13:03:34','2026-05-20 13:03:35'),(61,NULL,'Committee Demo SE Project 02',NULL,NULL,NULL,'software_engineering',5,1,NULL,NULL,NULL,'draft','2026-05-20',NULL,NULL,NULL,'2026-05-20 13:03:34','2026-05-20 13:03:35'),(62,NULL,'Committee Demo Security Project 01',NULL,NULL,NULL,'security',5,7,NULL,NULL,NULL,'draft','2026-05-20',NULL,NULL,NULL,'2026-05-20 13:03:34','2026-05-20 13:03:35'),(63,NULL,'Committee Demo Security Project 02',NULL,NULL,NULL,'security',5,7,NULL,NULL,NULL,'draft','2026-05-20',NULL,NULL,NULL,'2026-05-20 13:03:34','2026-05-20 13:03:35'),(64,NULL,'Committee Demo Database Project 01',NULL,NULL,NULL,'databases',5,5,NULL,NULL,NULL,'draft','2026-05-20',NULL,NULL,NULL,'2026-05-20 13:03:34','2026-05-20 13:03:35'),(65,NULL,'Committee Demo Database Project 02',NULL,NULL,NULL,'databases',5,5,NULL,NULL,NULL,'draft','2026-05-20',NULL,NULL,NULL,'2026-05-20 13:03:34','2026-05-20 13:03:35'),(66,NULL,'Committee Demo Mobile Project 01',NULL,NULL,NULL,'mobile',5,6,NULL,NULL,NULL,'draft','2026-05-20',NULL,NULL,NULL,'2026-05-20 13:03:34','2026-05-20 13:03:35'),(67,NULL,'Committee Demo Mobile Project 02',NULL,NULL,NULL,'mobile',5,6,NULL,NULL,NULL,'draft','2026-05-20',NULL,NULL,NULL,'2026-05-20 13:03:34','2026-05-20 13:03:35'),(71,NULL,'Smart Invoice',NULL,NULL,NULL,'ai',2,3,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,82.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(72,NULL,'Kitchen Station Management System',NULL,NULL,NULL,'web',2,4,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,79.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(73,NULL,'DreamsJob Recruitment Platform',NULL,NULL,NULL,'web',2,5,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,85.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(74,NULL,'YallaRehla Travel App',NULL,NULL,NULL,'mobile',2,6,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,88.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(75,NULL,'StudentHub',NULL,NULL,NULL,'web',2,7,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,76.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(76,NULL,'Wasselha Delivery System',NULL,NULL,NULL,'mobile',2,3,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,83.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(77,NULL,'Home Sweet Home Real Estate',NULL,NULL,NULL,'web',2,4,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,80.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(78,NULL,'Birzeit University Insurance System',NULL,NULL,NULL,'web',3,5,NULL,NULL,NULL,'archived','2024-02-01',NULL,NULL,91.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(79,NULL,'Sal7ly Maintenance App',NULL,NULL,NULL,'mobile',3,6,NULL,NULL,NULL,'archived','2024-02-01',NULL,NULL,78.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(80,NULL,'Monitoring World News System',NULL,NULL,NULL,'web',3,7,NULL,NULL,NULL,'archived','2024-02-01',NULL,NULL,74.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(81,NULL,'Prediction of Anti-Cancer Peptide ACP-XG',NULL,NULL,NULL,'ai',2,3,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,94.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(82,NULL,'FitScoop Fitness Platform',NULL,NULL,NULL,'mobile',2,4,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,81.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(83,NULL,'Wedding Planning System',NULL,NULL,NULL,'web',2,5,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,77.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(84,NULL,'PharmaApp Pharmacy Management',NULL,NULL,NULL,'mobile',2,6,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,86.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(85,NULL,'Student Digital Guide',NULL,NULL,NULL,'web',2,7,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,80.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(86,NULL,'Palestine Charity Platform',NULL,NULL,NULL,'web',2,3,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,75.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(87,NULL,'Gamified Trip Planner App',NULL,NULL,NULL,'mobile',2,4,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,89.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(88,NULL,'TechSpotter Tech News Platform',NULL,NULL,NULL,'web',2,5,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,78.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(89,NULL,'Multi-Environment Video Game',NULL,NULL,NULL,'other',2,6,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,83.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(90,NULL,'Birzeit Library Chatbot',NULL,NULL,NULL,'ai',2,7,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,92.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(91,NULL,'Policy Peek Policy Analyzer',NULL,NULL,NULL,'ai',2,3,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,87.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(92,NULL,'LifeActive Health Tracker',NULL,NULL,NULL,'mobile',2,4,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,84.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(93,NULL,'Tronix Electronics Web Application',NULL,NULL,NULL,'web',2,5,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,79.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(94,NULL,'Smart School Portal',NULL,NULL,NULL,'web',2,6,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,88.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(95,NULL,'GoHelp Volunteer Platform',NULL,NULL,NULL,'web',2,7,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,76.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(96,NULL,'KhatClarifier AI Writing Tool',NULL,NULL,NULL,'ai',2,3,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,90.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(97,NULL,'ConvoConvert Communication Tool',NULL,NULL,NULL,'ai',2,4,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,85.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(98,NULL,'Wasselni Transportation App',NULL,NULL,NULL,'mobile',2,5,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,82.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(99,NULL,'Ackerra Fitness Platform',NULL,NULL,NULL,'mobile',2,6,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,87.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(100,NULL,'Darak Real Estate Marketplace',NULL,NULL,NULL,'web',2,7,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,83.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(101,NULL,'Flora Palestine Plant Guide',NULL,NULL,NULL,'mobile',2,3,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,81.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(102,NULL,'Max Scheduling System',NULL,NULL,NULL,'web',2,4,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,77.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(103,NULL,'PayWithPalKoin Payment System',NULL,NULL,NULL,'web',2,5,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,86.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(104,NULL,'Nomad Travel Companion App',NULL,NULL,NULL,'mobile',2,6,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,84.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(105,NULL,'CarPal Car Sharing App',NULL,NULL,NULL,'mobile',2,7,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,88.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(106,NULL,'E-Voting System Using Blockchain',NULL,NULL,NULL,'security',3,3,NULL,NULL,NULL,'archived','2024-02-01',NULL,NULL,93.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(107,NULL,'Nossrah Arabic Learning App',NULL,NULL,NULL,'mobile',3,4,NULL,NULL,NULL,'archived','2024-02-01',NULL,NULL,80.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(108,NULL,'Wanderlust in Palestine Travel App',NULL,NULL,NULL,'web',3,5,NULL,NULL,NULL,'archived','2024-02-01',NULL,NULL,85.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(109,NULL,'Medica Healthcare App',NULL,NULL,NULL,'mobile',3,6,NULL,NULL,NULL,'archived','2024-02-01',NULL,NULL,82.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(110,NULL,'BZU Note Share App',NULL,NULL,NULL,'mobile',3,7,NULL,NULL,NULL,'archived','2024-02-01',NULL,NULL,79.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(111,NULL,'Plestia Events Platform',NULL,NULL,NULL,'web',3,3,NULL,NULL,NULL,'archived','2024-02-01',NULL,NULL,83.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(112,NULL,'Baby Voice Identification App',NULL,NULL,NULL,'ai',3,4,NULL,NULL,NULL,'archived','2024-02-01',NULL,NULL,88.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(113,NULL,'Traffic Light Synchronization Optimizer',NULL,NULL,NULL,'ai',3,5,NULL,NULL,NULL,'archived','2024-02-01',NULL,NULL,91.00,'2026-05-20 13:45:27','2026-05-20 13:45:27'),(114,NULL,'CampusConnect University Network',NULL,NULL,NULL,'web',3,6,NULL,NULL,NULL,'archived','2024-02-01',NULL,NULL,86.00,'2026-05-20 13:45:27','2026-05-20 13:45:27');
/*!40000 ALTER TABLE `projects` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `section_completion_status`
--

DROP TABLE IF EXISTS `section_completion_status`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `section_completion_status` (
  `status_id` int NOT NULL AUTO_INCREMENT,
  `course_scope` enum('introduction','graduation_project') NOT NULL,
  `reference_id` int NOT NULL,
  `status` enum('pending','succeeded','not_succeeded') NOT NULL DEFAULT 'pending',
  `notes` text,
  `marked_by` int DEFAULT NULL,
  `marked_at` datetime DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`status_id`),
  UNIQUE KEY `uq_section_completion` (`course_scope`,`reference_id`),
  KEY `idx_section_completion_status` (`status`),
  KEY `idx_section_completion_scope_status` (`course_scope`,`status`),
  KEY `marked_by` (`marked_by`),
  CONSTRAINT `section_completion_status_ibfk_1` FOREIGN KEY (`marked_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `section_completion_status`
--

LOCK TABLES `section_completion_status` WRITE;
/*!40000 ALTER TABLE `section_completion_status` DISABLE KEYS */;
/*!40000 ALTER TABLE `section_completion_status` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `section_students`
--

DROP TABLE IF EXISTS `section_students`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `section_students` (
  `id` int NOT NULL AUTO_INCREMENT,
  `section_id` int NOT NULL,
  `student_id` int NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_section_student` (`section_id`,`student_id`),
  KEY `student_id` (`student_id`),
  CONSTRAINT `section_students_ibfk_1` FOREIGN KEY (`section_id`) REFERENCES `student_distribution_sections` (`section_id`) ON DELETE CASCADE,
  CONSTRAINT `section_students_ibfk_2` FOREIGN KEY (`student_id`) REFERENCES `students` (`student_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `section_students`
--

LOCK TABLES `section_students` WRITE;
/*!40000 ALTER TABLE `section_students` DISABLE KEYS */;
/*!40000 ALTER TABLE `section_students` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `semesters`
--

DROP TABLE IF EXISTS `semesters`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `semesters` (
  `semester_id` int NOT NULL AUTO_INCREMENT,
  `academic_year` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'e.g. 2025/2026',
  `semester_number` tinyint NOT NULL COMMENT '1 or 2',
  `course_code` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'COMP4200',
  `start_date` date DEFAULT NULL,
  `end_date` date DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '0',
  `distribution_open` tinyint(1) NOT NULL DEFAULT '0',
  `distribution_opened_at` datetime DEFAULT NULL,
  `distribution_closed_at` datetime DEFAULT NULL,
  `distribution_close_at` datetime DEFAULT NULL,
  PRIMARY KEY (`semester_id`),
  UNIQUE KEY `uq_semester` (`academic_year`,`semester_number`)
) ENGINE=InnoDB AUTO_INCREMENT=16 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `semesters`
--

LOCK TABLES `semesters` WRITE;
/*!40000 ALTER TABLE `semesters` DISABLE KEYS */;
INSERT INTO `semesters` VALUES (1,'2025/2026',1,'COMP4200','2025-09-01','2026-02-28',1,0,NULL,NULL,NULL),(2,'2024/2025',1,'COMP4200','2024-09-01','2025-02-28',0,0,NULL,NULL,NULL),(3,'2023/2024',1,'COMP4200','2023-09-01','2024-02-28',0,0,NULL,NULL,NULL),(4,'2022/2023',1,'COMP4200','2022-09-01','2023-02-28',0,0,NULL,NULL,NULL),(5,'2025/2026',2,'COMP4300','2026-03-01','2026-07-01',1,0,NULL,NULL,NULL);
/*!40000 ALTER TABLE `semesters` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `student_course_results`
--

DROP TABLE IF EXISTS `student_course_results`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `student_course_results` (
  `result_id` int NOT NULL AUTO_INCREMENT,
  `student_id` int NOT NULL COMMENT 'Foreign key from students table',
  `semester_id` int NOT NULL COMMENT 'The semester in which the student is evaluated (COMP4200)',
  `status` enum('pending','passed','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `updated_by` int DEFAULT NULL COMMENT 'user_id of the coordinator',
  `notes` text COLLATE utf8mb4_unicode_ci,
  `promoted_to_semester_id` int DEFAULT NULL COMMENT 'semester_id for COMP4300 after passing',
  `promoted_by` int DEFAULT NULL COMMENT 'user_id of the head who promoted the student',
  `promoted_at` timestamp NULL DEFAULT NULL COMMENT 'Actual promotion timestamp',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`result_id`),
  UNIQUE KEY `uq_student_semester` (`student_id`,`semester_id`),
  KEY `updated_by` (`updated_by`),
  KEY `promoted_to_semester_id` (`promoted_to_semester_id`),
  KEY `promoted_by` (`promoted_by`),
  KEY `idx_scr_semester` (`semester_id`,`status`),
  KEY `idx_scr_passed_not_promoted` (`status`,`promoted_at`),
  CONSTRAINT `student_course_results_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `students` (`student_id`) ON DELETE CASCADE,
  CONSTRAINT `student_course_results_ibfk_2` FOREIGN KEY (`semester_id`) REFERENCES `semesters` (`semester_id`) ON DELETE RESTRICT,
  CONSTRAINT `student_course_results_ibfk_3` FOREIGN KEY (`updated_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL,
  CONSTRAINT `student_course_results_ibfk_4` FOREIGN KEY (`promoted_to_semester_id`) REFERENCES `semesters` (`semester_id`) ON DELETE SET NULL,
  CONSTRAINT `student_course_results_ibfk_5` FOREIGN KEY (`promoted_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=48 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Student results in COMP4200 — shared between coordinator and head';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `student_course_results`
--

LOCK TABLES `student_course_results` WRITE;
/*!40000 ALTER TABLE `student_course_results` DISABLE KEYS */;
INSERT INTO `student_course_results` VALUES (1,1,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(2,2,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(3,3,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(4,4,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(5,5,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(6,6,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(7,7,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(8,8,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(9,9,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(10,10,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(16,11,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(17,12,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(18,13,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(19,14,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(20,15,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(21,16,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(22,17,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(23,18,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(24,19,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(25,20,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(26,21,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(27,22,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(28,23,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(29,24,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(30,25,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(31,26,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(32,27,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(33,28,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(34,29,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(35,30,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(36,31,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(37,32,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(38,33,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(39,34,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02');
/*!40000 ALTER TABLE `student_course_results` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `student_courses`
--

DROP TABLE IF EXISTS `student_courses`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `student_courses` (
  `id` int NOT NULL AUTO_INCREMENT,
  `student_id` int NOT NULL,
  `semester_id` int NOT NULL,
  `status` enum('pending','active','rejected') COLLATE utf8mb4_unicode_ci DEFAULT 'pending',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `course_code` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  KEY `student_id` (`student_id`),
  KEY `semester_id` (`semester_id`),
  CONSTRAINT `student_courses_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `students` (`student_id`),
  CONSTRAINT `student_courses_ibfk_2` FOREIGN KEY (`semester_id`) REFERENCES `semesters` (`semester_id`)
) ENGINE=InnoDB AUTO_INCREMENT=16 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `student_courses`
--

LOCK TABLES `student_courses` WRITE;
/*!40000 ALTER TABLE `student_courses` DISABLE KEYS */;
INSERT INTO `student_courses` VALUES (11,1,1,'active','2026-05-02 12:54:55','COMP4200'),(12,2,1,'active','2026-05-02 12:54:55','COMP4200'),(13,3,1,'active','2026-05-02 12:54:55','COMP4200'),(14,9,5,'active','2026-05-02 13:02:51','COMP4300'),(15,10,5,'active','2026-05-02 13:02:51','COMP4300');
/*!40000 ALTER TABLE `student_courses` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `student_distribution_sections`
--

DROP TABLE IF EXISTS `student_distribution_sections`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `student_distribution_sections` (
  `section_id` int NOT NULL AUTO_INCREMENT,
  `section_name` varchar(100) NOT NULL,
  `supervisor_id` int NOT NULL,
  `entered_by` int DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`section_id`),
  KEY `supervisor_id` (`supervisor_id`),
  KEY `entered_by` (`entered_by`),
  CONSTRAINT `student_distribution_sections_ibfk_1` FOREIGN KEY (`supervisor_id`) REFERENCES `faculty` (`faculty_id`) ON DELETE CASCADE,
  CONSTRAINT `student_distribution_sections_ibfk_2` FOREIGN KEY (`entered_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `student_distribution_sections`
--

LOCK TABLES `student_distribution_sections` WRITE;
/*!40000 ALTER TABLE `student_distribution_sections` DISABLE KEYS */;
INSERT INTO `student_distribution_sections` VALUES (1,'COMP4200 Introduction Section 1',2,NULL,'2026-05-20 13:03:36'),(2,'COMP4200 Introduction Section 2',1,NULL,'2026-05-20 13:03:36'),(3,'COMP4200 Introduction Section 3',5,NULL,'2026-05-20 13:03:36');
/*!40000 ALTER TABLE `student_distribution_sections` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `student_groups`
--

DROP TABLE IF EXISTS `student_groups`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `student_groups` (
  `group_id` int NOT NULL COMMENT 'Shared group identifier for teammates',
  `student_id` int NOT NULL,
  PRIMARY KEY (`group_id`,`student_id`),
  KEY `student_id` (`student_id`),
  CONSTRAINT `student_groups_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `students` (`student_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Maps students to their project groups for duplicate-submission checks';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `student_groups`
--

LOCK TABLES `student_groups` WRITE;
/*!40000 ALTER TABLE `student_groups` DISABLE KEYS */;
/*!40000 ALTER TABLE `student_groups` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `students`
--

DROP TABLE IF EXISTS `students`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `students` (
  `student_id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `enrollment_year` year DEFAULT NULL,
  PRIMARY KEY (`student_id`),
  UNIQUE KEY `user_id` (`user_id`),
  CONSTRAINT `students_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=62 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `students`
--

LOCK TABLES `students` WRITE;
/*!40000 ALTER TABLE `students` DISABLE KEYS */;
INSERT INTO `students` VALUES (1,8,2022),(2,9,2022),(3,10,2022),(4,11,2022),(5,12,2022),(6,13,2021),(7,14,2022),(8,15,2022),(9,16,2021),(10,17,2022),(11,49,2022),(12,50,2022),(13,51,2022),(14,52,2022),(15,53,2022),(16,54,2022),(17,55,2022),(18,56,2022),(19,57,2022),(20,58,2022),(21,59,2022),(22,60,2022),(23,61,2022),(24,62,2022),(25,63,2022),(26,64,2022),(27,65,2022),(28,66,2022),(29,67,2022),(30,68,2022),(31,69,2022),(32,70,2022),(33,71,2022),(34,72,2022);
/*!40000 ALTER TABLE `students` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `supervisor_assignments`
--

DROP TABLE IF EXISTS `supervisor_assignments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `supervisor_assignments` (
  `sa_id` int NOT NULL AUTO_INCREMENT,
  `faculty_id` int NOT NULL,
  `project_id` int NOT NULL,
  `semester_id` int NOT NULL,
  `assigned_by` int NOT NULL COMMENT 'head of department user_id',
  `notes` text COLLATE utf8mb4_unicode_ci,
  `assigned_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`sa_id`),
  KEY `faculty_id` (`faculty_id`),
  KEY `project_id` (`project_id`),
  KEY `semester_id` (`semester_id`),
  KEY `assigned_by` (`assigned_by`),
  CONSTRAINT `supervisor_assignments_ibfk_1` FOREIGN KEY (`faculty_id`) REFERENCES `faculty` (`faculty_id`) ON DELETE RESTRICT,
  CONSTRAINT `supervisor_assignments_ibfk_2` FOREIGN KEY (`project_id`) REFERENCES `projects` (`project_id`) ON DELETE CASCADE,
  CONSTRAINT `supervisor_assignments_ibfk_3` FOREIGN KEY (`semester_id`) REFERENCES `semesters` (`semester_id`),
  CONSTRAINT `supervisor_assignments_ibfk_4` FOREIGN KEY (`assigned_by`) REFERENCES `users` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `supervisor_assignments`
--

LOCK TABLES `supervisor_assignments` WRITE;
/*!40000 ALTER TABLE `supervisor_assignments` DISABLE KEYS */;
/*!40000 ALTER TABLE `supervisor_assignments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `supervisor_notes`
--

DROP TABLE IF EXISTS `supervisor_notes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `supervisor_notes` (
  `note_id` int NOT NULL AUTO_INCREMENT,
  `project_id` int NOT NULL,
  `supervisor_id` int NOT NULL COMMENT 'faculty_id',
  `note_text` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `urgency` enum('on_track','needs_follow_up','urgent') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'on_track',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`note_id`),
  KEY `project_id` (`project_id`),
  KEY `supervisor_id` (`supervisor_id`),
  CONSTRAINT `supervisor_notes_ibfk_1` FOREIGN KEY (`project_id`) REFERENCES `projects` (`project_id`) ON DELETE CASCADE,
  CONSTRAINT `supervisor_notes_ibfk_2` FOREIGN KEY (`supervisor_id`) REFERENCES `faculty` (`faculty_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `supervisor_notes`
--

LOCK TABLES `supervisor_notes` WRITE;
/*!40000 ALTER TABLE `supervisor_notes` DISABLE KEYS */;
INSERT INTO `supervisor_notes` VALUES (4,1,3,'Team is working diligently and progress is satisfactory. Presentation slides still need to be uploaded before the deadline.','on_track','2026-05-20 13:45:01'),(5,3,5,'No files have been uploaded for two weeks — requires immediate follow-up.','urgent','2026-05-20 13:45:01'),(6,2,4,'Progress is slightly slow but still within acceptable range. Awaiting source code update.','needs_follow_up','2026-05-20 13:45:01'),(7,1,3,'Team is working diligently and progress is satisfactory. Presentation slides still need to be uploaded before the deadline.','on_track','2026-05-20 13:57:21'),(8,3,5,'No files have been uploaded for two weeks — requires immediate follow-up.','urgent','2026-05-20 13:57:21'),(9,2,4,'Progress is slightly slow but still within acceptable range. Awaiting source code update.','needs_follow_up','2026-05-20 13:57:21');
/*!40000 ALTER TABLE `supervisor_notes` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `system_notices`
--

DROP TABLE IF EXISTS `system_notices`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `system_notices` (
  `notice_id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `body` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `highlight_text` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `button1_text` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `button2_text` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `button3_text` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `course_scope` enum('introduction','graduation_project','both') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'both',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `updated_by` int DEFAULT NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`notice_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `system_notices`
--

LOCK TABLES `system_notices` WRITE;
/*!40000 ALTER TABLE `system_notices` DISABLE KEYS */;
/*!40000 ALTER TABLE `system_notices` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `user_id` int NOT NULL AUTO_INCREMENT,
  `university_id` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'University ID number',
  `full_name` varchar(120) COLLATE utf8mb4_unicode_ci NOT NULL,
  `email` varchar(150) COLLATE utf8mb4_unicode_ci NOT NULL,
  `password_hash` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `role` enum('student','supervisor','coordinator','head_of_department') COLLATE utf8mb4_unicode_ci NOT NULL,
  `avatar_initials` varchar(5) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Avatar initials for display',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`),
  UNIQUE KEY `university_id` (`university_id`),
  UNIQUE KEY `email` (`email`)
) ENGINE=InnoDB AUTO_INCREMENT=114 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES (1,'1001','Dr. Iyad Jaber','1001@birzeit.edu','$2b$12$EbPsSfvh6ScacL2l4uCkdOMwbfukrx0EdkL/0GBk/ntRtwRapvvBu','head_of_department','IJ',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(2,'1002','Dr. Ruba Awadallah','1002@birzeit.edu','$2b$12$l9Jz.shLtccTVJh5r700w.kCUlmwlba4YgUvs2HZGs2UBwuoonMci','coordinator','RA',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(3,'1003','Dr. Sobhi Ahmad','1003@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','SA',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(4,'1004','Dr. Radi Jarrar','1004@birzeit.edu','$2b$12$ctwodGi2uo7.QC.r7Qlt.u5n6wVvy280mQ/LtyaIlIjQLIVpgB/MW','supervisor','RJ',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(5,'1005','Dr. Abdullah Krakeh','1005@birzeit.edu','$2b$12$aKMFBXAIvKSNsOAUpU9N8.oYnCqeu07VJc/PBgyB.H7WIxxc4ew9C','supervisor','AK',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(6,'1006','Dr. Mamoun Nawahdah','1006@birzeit.edu','$2b$12$ljZY7r8ALYi62IyesXQ84uieyNMz2MXVJK.QI4Eu7ot9abWAa7TAG','supervisor','MN',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(7,'1007','Dr. Hafez Barghouthi','1007@birzeit.edu','$2b$12$.Uge.NmsvHbi9uSDgc1rhOYjO3Q1HAtYCLeN3YL1ctrGUKeRKo1ti','supervisor','HB',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(8,'1220654','Rahaf Badwan','1220654@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','RB',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(9,'1220670','Amna Abu Muslim','1220670@students.birzeit.edu','$2b$12$1ONCgGY62binf5lUfYs6qekRIUhkUObqIs55tu.89rGMGOAsp0Llu','student','AM',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(10,'1220174','Tima Abd','1220174@students.birzeit.edu','$2b$12$OxHQ1TKrYWOQ6UUw8pN15.APXR8zjzAvrJkpUPpnkDtJFPPAo92Z.','student','TA',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(11,'1220110','Salma Al-Khatib','1220110@students.birzeit.edu','$2b$12$vMKQhyFzsLAXJkchac2KyeS4L2N.cw9AWHSCnwupz/cfc8s3Tf43a','student','SK',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(12,'1220087','Karim Odeh','1220087@students.birzeit.edu','$2b$12$aXSk8fIneFnOLmEnPH72CetVM9RwKecmo6YySgL8Td0V5M/ZNC6YC','student','KO',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(13,'1220500','Amjad Al-Rimawi','1220500@students.birzeit.edu','$2b$12$KBaKlbUt93mL9.oY1xrFQ.U.kCXt2eqAOdTZDdWOGiKWm0AOPsjem','student','AR',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(14,'1220600','Sara Musa','1220600@students.birzeit.edu','$2b$12$x46jpXoonqATaqjWSIZwvO4Mnx39j4YFAsl6TAxhw7m6xwbA4j3BK','student','SM',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(15,'1220700','Khaled Mansour','1220700@students.birzeit.edu','$2b$12$UZ02VkxW0l/XRWRu/T5ireQ5fiRfRdS0IiRzxe5RlfqnSLAe59A9O','student','KM',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(16,'1220800','Dana Ibrahim','1220800@students.birzeit.edu','$2b$12$km.HzoX0aw6nFjI2m3U8sezhKNDXZh7IBlpH.CEwqZx/ZSEv2DYqy','student','DI',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(17,'1220900','Mona Nassar','1220900@students.birzeit.edu','$2b$12$m/RTVrKRx.lsECFuFa6yguuR1rRxZO8i0QAxQun/7ojQZjq6M7D3G','student','MN',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(18,'3006','Dr. Murad Njoum','murad.njoum@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','MN',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(19,'3007','Dr. Adel Taweel','adel.taweel@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','AT',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(20,'3008','Dr. Yousef Hassouneh','yousef.hassouneh@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','YH',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(21,'3010','Dr. Bassem Alserafi','bassem.alserafi@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','BA',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(22,'3012','Dr. Tasneem Zayt','tasneem.zayt@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','TZ',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(23,'3013','Dr. Samer Zein','samer.zein@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','SZ',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(24,'3015','Dr. Abdullah Al-Natsheh','abdullah.alnatsheh@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','AN',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(25,'3016','Dr. Alaa Hasheesh','alaa.hasheesh@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','AH',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(26,'3017','Dr. Faisal Shehadeh','faisal.shehadeh@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','FS',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(27,'3018','Dr. Fadi Khalil','fadi.khalil@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','FK',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(28,'3019','Dr. Mohammad Helal','mohammad.helal@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','MH',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(29,'3020','Dr. Rashid Yousef','rashid.yousef@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','RY',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(30,'3021','Dr. Ehab Alshaer','ehab.alshaer@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','EA',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(31,'3023','Dr. Ahmad Fahl','ahmad.fahl@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','AF',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(32,'3024','Dr. Ahmad Sabbah','ahmad.sabbah@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','AS',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(33,'3025','Dr. Mohammad Alkhanafseh','mohammad.alkhanafseh@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','MA',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(49,'1221001','Yousef Hamdan','1221001@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','YH',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(50,'1221002','Layan Daraghmeh','1221002@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','LD',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(51,'1221003','Noor Sawafta','1221003@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','NS',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(52,'1221004','Alaa Zakarneh','1221004@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','AZ',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(53,'1221005','Raneem Jaradat','1221005@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','RJ',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(54,'1221006','Malak Khoury','1221006@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','MK',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(55,'1221007','Hana Qasem','1221007@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','HQ',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(56,'1221008','Basil Jaber','1221008@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','BJ',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(57,'1221009','Jana Taqatqa','1221009@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','JT',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(58,'1221010','Omar Khatib','1221010@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','OK',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(59,'1221011','Reem Hammad','1221011@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','RH',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(60,'1221012','Yazan Abu Ayyash','1221012@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','YA',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(61,'1221013','Farah Odeh','1221013@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','FO',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(62,'1221014','Lina Barghouti','1221014@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','LB',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(63,'1221015','Mariam Salameh','1221015@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','MS',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(64,'1221016','Ali Shraim','1221016@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','AS',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(65,'1221017','Sama Dweikat','1221017@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','SD',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(66,'1221018','Husam Azzam','1221018@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','HA',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(67,'1221019','Aseel Masri','1221019@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','AM',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(68,'1221020','Rama Hamayel','1221020@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','RH',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(69,'1221021','Mahmoud Shtayyeh','1221021@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','MS',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(70,'1221022','Celine Nasser','1221022@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','CN',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(71,'1221023','Adam Zaid','1221023@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','AZ',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(72,'1221024','Shahd Abu Eisheh','1221024@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','SA',1,'2026-05-20 13:03:31','2026-05-20 13:03:31');
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Temporary view structure for view `vw_committee_results`
--

DROP TABLE IF EXISTS `vw_committee_results`;
/*!50001 DROP VIEW IF EXISTS `vw_committee_results`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `vw_committee_results` AS SELECT 
 1 AS `committee_id`,
 1 AS `project_id`,
 1 AS `project_title`,
 1 AS `discussion_date`,
 1 AS `discussion_time`,
 1 AS `room`,
 1 AS `status`,
 1 AS `final_average`,
 1 AS `member_count`,
 1 AS `evaluations_submitted`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `vw_coordinator_student_results`
--

DROP TABLE IF EXISTS `vw_coordinator_student_results`;
/*!50001 DROP VIEW IF EXISTS `vw_coordinator_student_results`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `vw_coordinator_student_results` AS SELECT 
 1 AS `result_id`,
 1 AS `student_id`,
 1 AS `user_id`,
 1 AS `student_name`,
 1 AS `university_id`,
 1 AS `email`,
 1 AS `academic_year`,
 1 AS `comp_course`,
 1 AS `semester_id`,
 1 AS `status`,
 1 AS `notes`,
 1 AS `result_updated_at`,
 1 AS `updated_by_name`,
 1 AS `promotion_status`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `vw_graduation_section_results`
--

DROP TABLE IF EXISTS `vw_graduation_section_results`;
/*!50001 DROP VIEW IF EXISTS `vw_graduation_section_results`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `vw_graduation_section_results` AS SELECT 
 1 AS `course_scope`,
 1 AS `reference_id`,
 1 AS `section_name`,
 1 AS `supervisor_id`,
 1 AS `supervisor_name`,
 1 AS `student_count`,
 1 AS `students`,
 1 AS `result_status`,
 1 AS `notes`,
 1 AS `marked_at`,
 1 AS `marked_by_name`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `vw_head_pending_promotion`
--

DROP TABLE IF EXISTS `vw_head_pending_promotion`;
/*!50001 DROP VIEW IF EXISTS `vw_head_pending_promotion`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `vw_head_pending_promotion` AS SELECT 
 1 AS `result_id`,
 1 AS `student_name`,
 1 AS `university_id`,
 1 AS `email`,
 1 AS `academic_year`,
 1 AS `from_course`,
 1 AS `to_course`,
 1 AS `comp4300_semester_id`,
 1 AS `status`,
 1 AS `notes`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `vw_introduction_section_results`
--

DROP TABLE IF EXISTS `vw_introduction_section_results`;
/*!50001 DROP VIEW IF EXISTS `vw_introduction_section_results`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `vw_introduction_section_results` AS SELECT 
 1 AS `course_scope`,
 1 AS `reference_id`,
 1 AS `section_name`,
 1 AS `supervisor_id`,
 1 AS `supervisor_name`,
 1 AS `student_count`,
 1 AS `students`,
 1 AS `result_status`,
 1 AS `notes`,
 1 AS `marked_at`,
 1 AS `marked_by_name`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `vw_project_summary`
--

DROP TABLE IF EXISTS `vw_project_summary`;
/*!50001 DROP VIEW IF EXISTS `vw_project_summary`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `vw_project_summary` AS SELECT 
 1 AS `project_id`,
 1 AS `title`,
 1 AS `title_en`,
 1 AS `project_type`,
 1 AS `status`,
 1 AS `submission_date`,
 1 AS `final_score`,
 1 AS `academic_year`,
 1 AS `semester_number`,
 1 AS `course_code`,
 1 AS `supervisor_name`,
 1 AS `supervisor_specialization`,
 1 AS `overall_progress`,
 1 AS `report_progress`,
 1 AS `code_progress`,
 1 AS `slides_progress`,
 1 AS `team_size`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `vw_real_graduation_projects`
--

DROP TABLE IF EXISTS `vw_real_graduation_projects`;
/*!50001 DROP VIEW IF EXISTS `vw_real_graduation_projects`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `vw_real_graduation_projects` AS SELECT 
 1 AS `project_id`,
 1 AS `section_name`,
 1 AS `supervisor_id`,
 1 AS `supervisor_name`,
 1 AS `student_count`,
 1 AS `students`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `vw_supervisor_performance`
--

DROP TABLE IF EXISTS `vw_supervisor_performance`;
/*!50001 DROP VIEW IF EXISTS `vw_supervisor_performance`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `vw_supervisor_performance` AS SELECT 
 1 AS `faculty_id`,
 1 AS `full_name`,
 1 AS `specialization`,
 1 AS `years_experience`,
 1 AS `academic_year`,
 1 AS `total_projects`,
 1 AS `avg_score`,
 1 AS `accepted_count`,
 1 AS `rejected_count`*/;
SET character_set_client = @saved_cs_client;

--
-- Final view structure for view `vw_committee_results`
--

/*!50001 DROP VIEW IF EXISTS `vw_committee_results`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `vw_committee_results` AS select `c`.`committee_id` AS `committee_id`,`c`.`project_id` AS `project_id`,`p`.`title` AS `project_title`,`c`.`discussion_date` AS `discussion_date`,`c`.`discussion_time` AS `discussion_time`,`c`.`room` AS `room`,`c`.`status` AS `status`,`c`.`final_average` AS `final_average`,count(`cm`.`cm_id`) AS `member_count`,sum(`cm`.`evaluation_submitted`) AS `evaluations_submitted` from ((`committees` `c` join `projects` `p` on((`p`.`project_id` = `c`.`project_id`))) left join `committee_members` `cm` on((`cm`.`committee_id` = `c`.`committee_id`))) group by `c`.`committee_id` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `vw_coordinator_student_results`
--

/*!50001 DROP VIEW IF EXISTS `vw_coordinator_student_results`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `vw_coordinator_student_results` AS select `scr`.`result_id` AS `result_id`,`st`.`student_id` AS `student_id`,`u`.`user_id` AS `user_id`,`u`.`full_name` AS `student_name`,`u`.`university_id` AS `university_id`,`u`.`email` AS `email`,`s_comp`.`academic_year` AS `academic_year`,`s_comp`.`course_code` AS `comp_course`,`scr`.`semester_id` AS `semester_id`,`scr`.`status` AS `status`,`scr`.`notes` AS `notes`,`scr`.`updated_at` AS `result_updated_at`,`u_coord`.`full_name` AS `updated_by_name`,(case when (`scr`.`promoted_at` is not null) then 'Promoted' when (`scr`.`status` = 'passed') then 'Passed - Not Promoted Yet' else NULL end) AS `promotion_status` from ((((`students` `st` join `users` `u` on((`u`.`user_id` = `st`.`user_id`))) left join `student_course_results` `scr` on((`scr`.`student_id` = `st`.`student_id`))) left join `semesters` `s_comp` on((`s_comp`.`semester_id` = `scr`.`semester_id`))) left join `users` `u_coord` on((`u_coord`.`user_id` = `scr`.`updated_by`))) order by `u`.`full_name` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `vw_graduation_section_results`
--

/*!50001 DROP VIEW IF EXISTS `vw_graduation_section_results`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `vw_graduation_section_results` AS select 'graduation_project' AS `course_scope`,`v`.`project_id` AS `reference_id`,`v`.`section_name` AS `section_name`,`v`.`supervisor_id` AS `supervisor_id`,`v`.`supervisor_name` AS `supervisor_name`,`v`.`student_count` AS `student_count`,`v`.`students` AS `students`,coalesce(`scs`.`status`,'pending') AS `result_status`,`scs`.`notes` AS `notes`,`scs`.`marked_at` AS `marked_at`,`marker`.`full_name` AS `marked_by_name` from ((`vw_real_graduation_projects` `v` left join `section_completion_status` `scs` on(((`scs`.`course_scope` = 'graduation_project') and (`scs`.`reference_id` = `v`.`project_id`)))) left join `users` `marker` on((`marker`.`user_id` = `scs`.`marked_by`))) */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `vw_head_pending_promotion`
--

/*!50001 DROP VIEW IF EXISTS `vw_head_pending_promotion`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `vw_head_pending_promotion` AS select `scr`.`result_id` AS `result_id`,`u`.`full_name` AS `student_name`,`u`.`university_id` AS `university_id`,`u`.`email` AS `email`,`s_comp`.`academic_year` AS `academic_year`,`s_comp`.`course_code` AS `from_course`,`s_next`.`course_code` AS `to_course`,`s_next`.`semester_id` AS `comp4300_semester_id`,`scr`.`status` AS `status`,`scr`.`notes` AS `notes` from ((((`student_course_results` `scr` join `students` `st` on((`st`.`student_id` = `scr`.`student_id`))) join `users` `u` on((`u`.`user_id` = `st`.`user_id`))) join `semesters` `s_comp` on((`s_comp`.`semester_id` = `scr`.`semester_id`))) left join `semesters` `s_next` on(((`s_next`.`academic_year` = `s_comp`.`academic_year`) and (`s_next`.`course_code` = 'COMP4300')))) where ((`scr`.`status` = 'passed') and (`scr`.`promoted_at` is null)) order by `u`.`full_name` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `vw_introduction_section_results`
--

/*!50001 DROP VIEW IF EXISTS `vw_introduction_section_results`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `vw_introduction_section_results` AS select 'introduction' AS `course_scope`,`sds`.`section_id` AS `reference_id`,`sds`.`section_name` AS `section_name`,`sds`.`supervisor_id` AS `supervisor_id`,`u_sup`.`full_name` AS `supervisor_name`,count(distinct `ss`.`student_id`) AS `student_count`,coalesce(group_concat(distinct `u_st`.`full_name` order by `u_st`.`full_name` ASC separator ', '),'') AS `students`,coalesce(`scs`.`status`,'pending') AS `result_status`,`scs`.`notes` AS `notes`,`scs`.`marked_at` AS `marked_at`,`marker`.`full_name` AS `marked_by_name` from (((((((`student_distribution_sections` `sds` join `faculty` `f_sup` on((`f_sup`.`faculty_id` = `sds`.`supervisor_id`))) join `users` `u_sup` on((`u_sup`.`user_id` = `f_sup`.`user_id`))) left join `section_students` `ss` on((`ss`.`section_id` = `sds`.`section_id`))) left join `students` `st` on((`st`.`student_id` = `ss`.`student_id`))) left join `users` `u_st` on((`u_st`.`user_id` = `st`.`user_id`))) left join `section_completion_status` `scs` on(((`scs`.`course_scope` = 'introduction') and (`scs`.`reference_id` = `sds`.`section_id`)))) left join `users` `marker` on((`marker`.`user_id` = `scs`.`marked_by`))) group by `sds`.`section_id`,`sds`.`section_name`,`sds`.`supervisor_id`,`u_sup`.`full_name`,`scs`.`status`,`scs`.`notes`,`scs`.`marked_at`,`marker`.`full_name` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `vw_project_summary`
--

/*!50001 DROP VIEW IF EXISTS `vw_project_summary`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `vw_project_summary` AS select `p`.`project_id` AS `project_id`,`p`.`title` AS `title`,`p`.`title_en` AS `title_en`,`p`.`project_type` AS `project_type`,`p`.`status` AS `status`,`p`.`submission_date` AS `submission_date`,`p`.`final_score` AS `final_score`,`s`.`academic_year` AS `academic_year`,`s`.`semester_number` AS `semester_number`,`s`.`course_code` AS `course_code`,`u_sup`.`full_name` AS `supervisor_name`,`f_sup`.`specialization` AS `supervisor_specialization`,`pp_overall`.`percentage` AS `overall_progress`,`pp_report`.`percentage` AS `report_progress`,`pp_code`.`percentage` AS `code_progress`,`pp_slides`.`percentage` AS `slides_progress`,count(distinct `pm`.`student_id`) AS `team_size` from ((((((((`projects` `p` join `semesters` `s` on((`s`.`semester_id` = `p`.`semester_id`))) left join `faculty` `f_sup` on((`f_sup`.`faculty_id` = `p`.`supervisor_id`))) left join `users` `u_sup` on((`u_sup`.`user_id` = `f_sup`.`user_id`))) left join `project_members` `pm` on((`pm`.`project_id` = `p`.`project_id`))) left join `project_progress` `pp_overall` on(((`pp_overall`.`project_id` = `p`.`project_id`) and (`pp_overall`.`component` = 'overall')))) left join `project_progress` `pp_report` on(((`pp_report`.`project_id` = `p`.`project_id`) and (`pp_report`.`component` = 'final_report')))) left join `project_progress` `pp_code` on(((`pp_code`.`project_id` = `p`.`project_id`) and (`pp_code`.`component` = 'source_code')))) left join `project_progress` `pp_slides` on(((`pp_slides`.`project_id` = `p`.`project_id`) and (`pp_slides`.`component` = 'presentation')))) group by `p`.`project_id` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `vw_real_graduation_projects`
--

/*!50001 DROP VIEW IF EXISTS `vw_real_graduation_projects`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `vw_real_graduation_projects` AS select `p`.`project_id` AS `project_id`,concat('Group ',`p`.`project_id`) AS `section_name`,`p`.`supervisor_id` AS `supervisor_id`,`u_sup`.`full_name` AS `supervisor_name`,count(distinct `pm`.`student_id`) AS `student_count`,group_concat(distinct `u_st`.`full_name` order by `u_st`.`full_name` ASC separator ', ') AS `students` from ((((((`projects` `p` join `semesters` `sem` on((`sem`.`semester_id` = `p`.`semester_id`))) join `project_members` `pm` on((`pm`.`project_id` = `p`.`project_id`))) join `students` `st` on((`st`.`student_id` = `pm`.`student_id`))) join `users` `u_st` on((`u_st`.`user_id` = `st`.`user_id`))) left join `faculty` `f_sup` on((`f_sup`.`faculty_id` = `p`.`supervisor_id`))) left join `users` `u_sup` on((`u_sup`.`user_id` = `f_sup`.`user_id`))) where ((`sem`.`course_code` in ('COMP4300','COMP4201')) and (not((`p`.`title` like 'Committee Demo%')))) group by `p`.`project_id`,`p`.`supervisor_id`,`u_sup`.`full_name` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `vw_supervisor_performance`
--

/*!50001 DROP VIEW IF EXISTS `vw_supervisor_performance`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `vw_supervisor_performance` AS select `f`.`faculty_id` AS `faculty_id`,`u`.`full_name` AS `full_name`,`f`.`specialization` AS `specialization`,`f`.`years_experience` AS `years_experience`,`s`.`academic_year` AS `academic_year`,count(distinct `p`.`project_id`) AS `total_projects`,avg(`p`.`final_score`) AS `avg_score`,sum((`p`.`status` = 'accepted')) AS `accepted_count`,sum((`p`.`status` = 'rejected')) AS `rejected_count` from (((`faculty` `f` join `users` `u` on((`u`.`user_id` = `f`.`user_id`))) left join `projects` `p` on((`p`.`supervisor_id` = `f`.`faculty_id`))) left join `semesters` `s` on((`s`.`semester_id` = `p`.`semester_id`))) where (`u`.`role` = 'supervisor') group by `f`.`faculty_id`,`s`.`academic_year` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-05-20 16:59:56
