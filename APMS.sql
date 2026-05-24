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
) ENGINE=InnoDB AUTO_INCREMENT=121 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
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
-- Table structure for table `committee_plan_sections`
--

DROP TABLE IF EXISTS `committee_plan_sections`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `committee_plan_sections` (
  `id` int NOT NULL AUTO_INCREMENT,
  `plan_id` int NOT NULL,
  `section_id` int NOT NULL,
  `slot_order` int NOT NULL,
  `slot_start` time NOT NULL,
  `slot_end` time NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_committee_plan_section` (`plan_id`,`section_id`),
  UNIQUE KEY `uq_unique_section_committee` (`section_id`),
  KEY `idx_committee_plan_sections_plan` (`plan_id`),
  KEY `idx_committee_plan_sections_section` (`section_id`),
  CONSTRAINT `committee_plan_sections_ibfk_1` FOREIGN KEY (`plan_id`) REFERENCES `committee_plans` (`plan_id`) ON DELETE CASCADE,
  CONSTRAINT `committee_plan_sections_ibfk_2` FOREIGN KEY (`section_id`) REFERENCES `student_distribution_sections` (`section_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `committee_plan_sections`
--

LOCK TABLES `committee_plan_sections` WRITE;
/*!40000 ALTER TABLE `committee_plan_sections` DISABLE KEYS */;
/*!40000 ALTER TABLE `committee_plan_sections` ENABLE KEYS */;
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
) ENGINE=InnoDB AUTO_INCREMENT=37 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
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
) ENGINE=InnoDB AUTO_INCREMENT=16 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `coordinator_assignments`
--

LOCK TABLES `coordinator_assignments` WRITE;
/*!40000 ALTER TABLE `coordinator_assignments` DISABLE KEYS */;
INSERT INTO `coordinator_assignments` VALUES (9,2,1,2,'Official coordinator for Semester 1 — 2025/2026','2026-05-24 20:22:02'),(11,2,5,2,NULL,'2026-05-24 20:22:02');
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
) ENGINE=InnoDB AUTO_INCREMENT=49 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `coordinator_decisions`
--

LOCK TABLES `coordinator_decisions` WRITE;
/*!40000 ALTER TABLE `coordinator_decisions` DISABLE KEYS */;
INSERT INTO `coordinator_decisions` VALUES (5,4,2,'send_to_committee','Project accepted and forwarded to committee evaluation after a satisfactory initial review.','2026-05-20 13:45:01'),(6,5,2,'accepted','Excellent project — archiving completed successfully.','2026-05-20 13:45:01'),(7,7,2,'rejected','Project score is below the minimum required threshold of 60%.','2026-05-20 13:45:01'),(8,6,2,'needs_revision','Student must add a security and privacy section and clarify the patient data protection protocol.','2026-05-20 13:45:01'),(9,4,2,'send_to_committee','Project accepted and forwarded to committee evaluation after a satisfactory initial review.','2026-05-20 13:57:21'),(10,5,2,'accepted','Excellent project — archiving completed successfully.','2026-05-20 13:57:21'),(11,7,2,'rejected','Project score is below the minimum required threshold of 60%.','2026-05-20 13:57:21'),(12,6,2,'needs_revision','Student must add a security and privacy section and clarify the patient data protection protocol.','2026-05-20 13:57:21'),(13,4,2,'send_to_committee','Project accepted and forwarded to committee evaluation after a satisfactory initial review.','2026-05-22 17:27:43'),(14,5,2,'accepted','Excellent project — archiving completed successfully.','2026-05-22 17:27:43'),(15,7,2,'rejected','Project score is below the minimum required threshold of 60%.','2026-05-22 17:27:43'),(16,6,2,'needs_revision','Student must add a security and privacy section and clarify the patient data protection protocol.','2026-05-22 17:27:43'),(17,4,2,'send_to_committee','Project accepted and forwarded to committee evaluation after a satisfactory initial review.','2026-05-22 17:30:09'),(18,5,2,'accepted','Excellent project — archiving completed successfully.','2026-05-22 17:30:09'),(19,7,2,'rejected','Project score is below the minimum required threshold of 60%.','2026-05-22 17:30:09'),(20,6,2,'needs_revision','Student must add a security and privacy section and clarify the patient data protection protocol.','2026-05-22 17:30:09'),(21,4,2,'send_to_committee','Project accepted and forwarded to committee evaluation after a satisfactory initial review.','2026-05-24 12:40:12'),(22,5,2,'accepted','Excellent project — archiving completed successfully.','2026-05-24 12:40:12'),(23,7,2,'rejected','Project score is below the minimum required threshold of 60%.','2026-05-24 12:40:12'),(24,6,2,'needs_revision','Student must add a security and privacy section and clarify the patient data protection protocol.','2026-05-24 12:40:12'),(25,4,2,'send_to_committee','Project accepted and forwarded to committee evaluation after a satisfactory initial review.','2026-05-24 19:44:30'),(26,5,2,'accepted','Excellent project — archiving completed successfully.','2026-05-24 19:44:30'),(27,7,2,'rejected','Project score is below the minimum required threshold of 60%.','2026-05-24 19:44:30'),(28,6,2,'needs_revision','Student must add a security and privacy section and clarify the patient data protection protocol.','2026-05-24 19:44:30'),(29,4,2,'send_to_committee','Project accepted and forwarded to committee evaluation after a satisfactory initial review.','2026-05-24 19:54:38'),(30,5,2,'accepted','Excellent project — archiving completed successfully.','2026-05-24 19:54:38'),(31,7,2,'rejected','Project score is below the minimum required threshold of 60%.','2026-05-24 19:54:38'),(32,6,2,'needs_revision','Student must add a security and privacy section and clarify the patient data protection protocol.','2026-05-24 19:54:38'),(33,4,2,'send_to_committee','Project accepted and forwarded to committee evaluation after a satisfactory initial review.','2026-05-24 20:13:39'),(34,5,2,'accepted','Excellent project — archiving completed successfully.','2026-05-24 20:13:39'),(35,7,2,'rejected','Project score is below the minimum required threshold of 60%.','2026-05-24 20:13:39'),(36,6,2,'needs_revision','Student must add a security and privacy section and clarify the patient data protection protocol.','2026-05-24 20:13:39'),(37,4,2,'send_to_committee','Project accepted and forwarded to committee evaluation after a satisfactory initial review.','2026-05-24 20:21:31'),(38,5,2,'accepted','Excellent project — archiving completed successfully.','2026-05-24 20:21:31'),(39,7,2,'rejected','Project score is below the minimum required threshold of 60%.','2026-05-24 20:21:31'),(40,6,2,'needs_revision','Student must add a security and privacy section and clarify the patient data protection protocol.','2026-05-24 20:21:31'),(41,4,2,'send_to_committee','Project accepted and forwarded to committee evaluation after a satisfactory initial review.','2026-05-24 22:16:42'),(42,5,2,'accepted','Excellent project — archiving completed successfully.','2026-05-24 22:16:42'),(43,7,2,'rejected','Project score is below the minimum required threshold of 60%.','2026-05-24 22:16:42'),(44,6,2,'needs_revision','Student must add a security and privacy section and clarify the patient data protection protocol.','2026-05-24 22:16:42'),(45,4,2,'send_to_committee','Project accepted and forwarded to committee evaluation after a satisfactory initial review.','2026-05-24 22:21:47'),(46,5,2,'accepted','Excellent project — archiving completed successfully.','2026-05-24 22:21:47'),(47,7,2,'rejected','Project score is below the minimum required threshold of 60%.','2026-05-24 22:21:47'),(48,6,2,'needs_revision','Student must add a security and privacy section and clarify the patient data protection protocol.','2026-05-24 22:21:47');
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
  `start_at` datetime DEFAULT NULL,
  `due_date` date DEFAULT NULL,
  `due_at` datetime DEFAULT NULL,
  `mark_points` decimal(5,2) NOT NULL DEFAULT '0.00',
  `status` enum('not_open','open','in_progress','completed','closed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'not_open',
  `is_published` tinyint(1) NOT NULL DEFAULT '0',
  `published_at` datetime DEFAULT NULL,
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
) ENGINE=InnoDB AUTO_INCREMENT=73 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `deadlines`
--

LOCK TABLES `deadlines` WRITE;
/*!40000 ALTER TABLE `deadlines` DISABLE KEYS */;
INSERT INTO `deadlines` VALUES (1,1,NULL,'project_registration','2026-02-15','Deadline for all project registrations'),(2,1,NULL,'file_submission','2026-02-15','Deadline for uploading all required project files'),(3,1,NULL,'results_announcement','2026-02-28','Final results announcement date'),(7,1,NULL,'project_registration','2026-02-15','Deadline for all project registrations'),(8,1,NULL,'file_submission','2026-02-15','Deadline for uploading all required project files'),(9,1,NULL,'results_announcement','2026-02-28','Final results announcement date'),(10,1,1,'final_report_submission','2026-02-15','Final report submission deadline — APMS project'),(11,1,1,'committee_discussion','2026-02-20','APMS project committee discussion date'),(12,1,1,'supervisor_feedback','2026-02-08','Deadline for supervisor feedback on APMS report'),(13,1,NULL,'project_registration','2026-02-15','Deadline for all project registrations'),(14,1,NULL,'file_submission','2026-02-15','Deadline for uploading all required project files'),(15,1,NULL,'results_announcement','2026-02-28','Final results announcement date'),(16,1,1,'final_report_submission','2026-02-15','Final report submission deadline — APMS project'),(17,1,1,'committee_discussion','2026-02-20','APMS project committee discussion date'),(18,1,1,'supervisor_feedback','2026-02-08','Deadline for supervisor feedback on APMS report'),(19,1,NULL,'project_registration','2026-02-15','Deadline for all project registrations'),(20,1,NULL,'file_submission','2026-02-15','Deadline for uploading all required project files'),(21,1,NULL,'results_announcement','2026-02-28','Final results announcement date'),(22,1,1,'final_report_submission','2026-02-15','Final report submission deadline — APMS project'),(23,1,1,'committee_discussion','2026-02-20','APMS project committee discussion date'),(24,1,1,'supervisor_feedback','2026-02-08','Deadline for supervisor feedback on APMS report'),(25,1,NULL,'project_registration','2026-02-15','Deadline for all project registrations'),(26,1,NULL,'file_submission','2026-02-15','Deadline for uploading all required project files'),(27,1,NULL,'results_announcement','2026-02-28','Final results announcement date'),(28,1,1,'final_report_submission','2026-02-15','Final report submission deadline — APMS project'),(29,1,1,'committee_discussion','2026-02-20','APMS project committee discussion date'),(30,1,1,'supervisor_feedback','2026-02-08','Deadline for supervisor feedback on APMS report'),(31,1,NULL,'project_registration','2026-02-15','Deadline for all project registrations'),(32,1,NULL,'file_submission','2026-02-15','Deadline for uploading all required project files'),(33,1,NULL,'results_announcement','2026-02-28','Final results announcement date'),(34,1,1,'final_report_submission','2026-02-15','Final report submission deadline — APMS project'),(35,1,1,'committee_discussion','2026-02-20','APMS project committee discussion date'),(36,1,1,'supervisor_feedback','2026-02-08','Deadline for supervisor feedback on APMS report'),(37,1,NULL,'project_registration','2026-02-15','Deadline for all project registrations'),(38,1,NULL,'file_submission','2026-02-15','Deadline for uploading all required project files'),(39,1,NULL,'results_announcement','2026-02-28','Final results announcement date'),(40,1,1,'final_report_submission','2026-02-15','Final report submission deadline — APMS project'),(41,1,1,'committee_discussion','2026-02-20','APMS project committee discussion date'),(42,1,1,'supervisor_feedback','2026-02-08','Deadline for supervisor feedback on APMS report'),(43,1,NULL,'project_registration','2026-02-15','Deadline for all project registrations'),(44,1,NULL,'file_submission','2026-02-15','Deadline for uploading all required project files'),(45,1,NULL,'results_announcement','2026-02-28','Final results announcement date'),(46,1,1,'final_report_submission','2026-02-15','Final report submission deadline — APMS project'),(47,1,1,'committee_discussion','2026-02-20','APMS project committee discussion date'),(48,1,1,'supervisor_feedback','2026-02-08','Deadline for supervisor feedback on APMS report'),(49,1,NULL,'project_registration','2026-02-15','Deadline for all project registrations'),(50,1,NULL,'file_submission','2026-02-15','Deadline for uploading all required project files'),(51,1,NULL,'results_announcement','2026-02-28','Final results announcement date'),(52,1,1,'final_report_submission','2026-02-15','Final report submission deadline — APMS project'),(53,1,1,'committee_discussion','2026-02-20','APMS project committee discussion date'),(54,1,1,'supervisor_feedback','2026-02-08','Deadline for supervisor feedback on APMS report'),(55,1,NULL,'project_registration','2026-02-15','Deadline for all project registrations'),(56,1,NULL,'file_submission','2026-02-15','Deadline for uploading all required project files'),(57,1,NULL,'results_announcement','2026-02-28','Final results announcement date'),(58,1,1,'final_report_submission','2026-02-15','Final report submission deadline — APMS project'),(59,1,1,'committee_discussion','2026-02-20','APMS project committee discussion date'),(60,1,1,'supervisor_feedback','2026-02-08','Deadline for supervisor feedback on APMS report'),(61,1,NULL,'project_registration','2026-02-15','Deadline for all project registrations'),(62,1,NULL,'file_submission','2026-02-15','Deadline for uploading all required project files'),(63,1,NULL,'results_announcement','2026-02-28','Final results announcement date'),(64,1,1,'final_report_submission','2026-02-15','Final report submission deadline — APMS project'),(65,1,1,'committee_discussion','2026-02-20','APMS project committee discussion date'),(66,1,1,'supervisor_feedback','2026-02-08','Deadline for supervisor feedback on APMS report'),(67,1,NULL,'project_registration','2026-02-15','Deadline for all project registrations'),(68,1,NULL,'file_submission','2026-02-15','Deadline for uploading all required project files'),(69,1,NULL,'results_announcement','2026-02-28','Final results announcement date'),(70,1,1,'final_report_submission','2026-02-15','Final report submission deadline — APMS project'),(71,1,1,'committee_discussion','2026-02-20','APMS project committee discussion date'),(72,1,1,'supervisor_feedback','2026-02-08','Deadline for supervisor feedback on APMS report');
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
) ENGINE=InnoDB AUTO_INCREMENT=64 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
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
-- Table structure for table `evaluation_final_results`
--

DROP TABLE IF EXISTS `evaluation_final_results`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `evaluation_final_results` (
  `result_id` int NOT NULL AUTO_INCREMENT,
  `course_scope` enum('introduction','graduation_project') NOT NULL,
  `reference_id` int NOT NULL COMMENT 'COMP4200: section_id, COMP4300: project_id',
  `report_score` decimal(6,2) DEFAULT NULL,
  `supervisor_score` decimal(6,2) DEFAULT NULL,
  `discussion_score` decimal(6,2) DEFAULT NULL,
  `committee_score` decimal(6,2) DEFAULT NULL,
  `final_score` decimal(6,2) DEFAULT NULL,
  `decision` enum('pending','accepted','rejected','archived') NOT NULL DEFAULT 'pending',
  `notes` text,
  `workflow_status` enum('draft','sent_to_supervisor','sent_to_head','published_to_students') NOT NULL DEFAULT 'draft',
  `sent_by_coordinator` int DEFAULT NULL COMMENT 'coordinator user_id',
  `sent_to_supervisor_at` datetime DEFAULT NULL,
  `supervisor_id` int DEFAULT NULL COMMENT 'supervisor faculty_id',
  `supervisor_sent_by` int DEFAULT NULL COMMENT 'supervisor user_id',
  `supervisor_sent_to_head_at` datetime DEFAULT NULL,
  `head_published_by` int DEFAULT NULL COMMENT 'head_of_department user_id',
  `head_published_at` datetime DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`result_id`),
  UNIQUE KEY `uq_eval_final_result_ref` (`course_scope`,`reference_id`),
  KEY `idx_eval_final_workflow` (`course_scope`,`workflow_status`),
  KEY `idx_eval_final_supervisor` (`supervisor_id`),
  KEY `sent_by_coordinator` (`sent_by_coordinator`),
  KEY `supervisor_sent_by` (`supervisor_sent_by`),
  KEY `head_published_by` (`head_published_by`),
  CONSTRAINT `evaluation_final_results_ibfk_1` FOREIGN KEY (`sent_by_coordinator`) REFERENCES `users` (`user_id`) ON DELETE SET NULL,
  CONSTRAINT `evaluation_final_results_ibfk_2` FOREIGN KEY (`supervisor_id`) REFERENCES `faculty` (`faculty_id`) ON DELETE SET NULL,
  CONSTRAINT `evaluation_final_results_ibfk_3` FOREIGN KEY (`supervisor_sent_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL,
  CONSTRAINT `evaluation_final_results_ibfk_4` FOREIGN KEY (`head_published_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `evaluation_final_results`
--

LOCK TABLES `evaluation_final_results` WRITE;
/*!40000 ALTER TABLE `evaluation_final_results` DISABLE KEYS */;
/*!40000 ALTER TABLE `evaluation_final_results` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `evaluation_grade_tasks`
--

DROP TABLE IF EXISTS `evaluation_grade_tasks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `evaluation_grade_tasks` (
  `task_id` int NOT NULL AUTO_INCREMENT,
  `course_scope` enum('introduction','graduation_project') NOT NULL,
  `reference_id` int NOT NULL,
  `component` varchar(60) NOT NULL,
  `evaluator_faculty_id` int NOT NULL,
  `max_mark` decimal(6,2) NOT NULL DEFAULT '0.00',
  `mark` decimal(6,2) DEFAULT NULL,
  `notes` text,
  `is_submitted` tinyint(1) NOT NULL DEFAULT '0',
  `created_by` int DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `submitted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`task_id`),
  UNIQUE KEY `uq_eval_task` (`course_scope`,`reference_id`,`component`,`evaluator_faculty_id`),
  KEY `idx_eval_task_ref` (`course_scope`,`reference_id`),
  KEY `idx_eval_task_eval` (`evaluator_faculty_id`),
  CONSTRAINT `fk_eval_task_faculty` FOREIGN KEY (`evaluator_faculty_id`) REFERENCES `faculty` (`faculty_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `evaluation_grade_tasks`
--

LOCK TABLES `evaluation_grade_tasks` WRITE;
/*!40000 ALTER TABLE `evaluation_grade_tasks` DISABLE KEYS */;
/*!40000 ALTER TABLE `evaluation_grade_tasks` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `evaluation_windows`
--

DROP TABLE IF EXISTS `evaluation_windows`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `evaluation_windows` (
  `window_id` int NOT NULL AUTO_INCREMENT,
  `course_scope` enum('introduction','graduation_project') NOT NULL,
  `reference_id` int NOT NULL,
  `is_open` tinyint(1) NOT NULL DEFAULT '0',
  `opened_by` int DEFAULT NULL,
  `opened_at` datetime DEFAULT NULL,
  `closed_at` datetime DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`window_id`),
  UNIQUE KEY `uq_eval_window` (`course_scope`,`reference_id`),
  KEY `idx_eval_window_scope_open` (`course_scope`,`is_open`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `evaluation_windows`
--

LOCK TABLES `evaluation_windows` WRITE;
/*!40000 ALTER TABLE `evaluation_windows` DISABLE KEYS */;
/*!40000 ALTER TABLE `evaluation_windows` ENABLE KEYS */;
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
) ENGINE=InnoDB AUTO_INCREMENT=116 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
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
) ENGINE=InnoDB AUTO_INCREMENT=49 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `feedback`
--

LOCK TABLES `feedback` WRITE;
/*!40000 ALTER TABLE `feedback` DISABLE KEYS */;
INSERT INTO `feedback` VALUES (5,1,3,'final_report_review','The report is generally well-written. I recommend clarifying the system architecture section further and adding detailed ERD diagrams. Please also ensure consistent use of technical terminology across all chapters.',78.00,'important',0,'2026-05-20 13:45:01'),(6,1,4,'committee_evaluation','The AI section needs more detail, particularly regarding the chatbot training methodology and accuracy evaluation. I recommend adding a comparison table of the NLP models used.',75.00,'normal',0,'2026-05-20 13:45:01'),(7,1,5,'committee_evaluation','The proposed UI is well thought out and appropriate. I recommend addressing accessibility requirements (WCAG) and adding support for users with special needs.',82.00,'normal',0,'2026-05-20 13:45:01'),(8,2,4,'source_code_review','The code is well-structured, but you need to add documentation comments to all major functions and write unit tests for sensitive operations such as authentication and role checking.',71.00,'normal',0,'2026-05-20 13:45:01'),(9,1,3,'final_report_review','The report is generally well-written. I recommend clarifying the system architecture section further and adding detailed ERD diagrams. Please also ensure consistent use of technical terminology across all chapters.',78.00,'important',0,'2026-05-20 13:57:21'),(10,1,4,'committee_evaluation','The AI section needs more detail, particularly regarding the chatbot training methodology and accuracy evaluation. I recommend adding a comparison table of the NLP models used.',75.00,'normal',0,'2026-05-20 13:57:21'),(11,1,5,'committee_evaluation','The proposed UI is well thought out and appropriate. I recommend addressing accessibility requirements (WCAG) and adding support for users with special needs.',82.00,'normal',0,'2026-05-20 13:57:21'),(12,2,4,'source_code_review','The code is well-structured, but you need to add documentation comments to all major functions and write unit tests for sensitive operations such as authentication and role checking.',71.00,'normal',0,'2026-05-20 13:57:21'),(13,1,3,'final_report_review','The report is generally well-written. I recommend clarifying the system architecture section further and adding detailed ERD diagrams. Please also ensure consistent use of technical terminology across all chapters.',78.00,'important',0,'2026-05-22 17:27:43'),(14,1,4,'committee_evaluation','The AI section needs more detail, particularly regarding the chatbot training methodology and accuracy evaluation. I recommend adding a comparison table of the NLP models used.',75.00,'normal',0,'2026-05-22 17:27:43'),(15,1,5,'committee_evaluation','The proposed UI is well thought out and appropriate. I recommend addressing accessibility requirements (WCAG) and adding support for users with special needs.',82.00,'normal',0,'2026-05-22 17:27:43'),(16,2,4,'source_code_review','The code is well-structured, but you need to add documentation comments to all major functions and write unit tests for sensitive operations such as authentication and role checking.',71.00,'normal',0,'2026-05-22 17:27:43'),(17,1,3,'final_report_review','The report is generally well-written. I recommend clarifying the system architecture section further and adding detailed ERD diagrams. Please also ensure consistent use of technical terminology across all chapters.',78.00,'important',0,'2026-05-22 17:30:09'),(18,1,4,'committee_evaluation','The AI section needs more detail, particularly regarding the chatbot training methodology and accuracy evaluation. I recommend adding a comparison table of the NLP models used.',75.00,'normal',0,'2026-05-22 17:30:09'),(19,1,5,'committee_evaluation','The proposed UI is well thought out and appropriate. I recommend addressing accessibility requirements (WCAG) and adding support for users with special needs.',82.00,'normal',0,'2026-05-22 17:30:09'),(20,2,4,'source_code_review','The code is well-structured, but you need to add documentation comments to all major functions and write unit tests for sensitive operations such as authentication and role checking.',71.00,'normal',0,'2026-05-22 17:30:09'),(21,1,3,'final_report_review','The report is generally well-written. I recommend clarifying the system architecture section further and adding detailed ERD diagrams. Please also ensure consistent use of technical terminology across all chapters.',78.00,'important',0,'2026-05-24 12:40:12'),(22,1,4,'committee_evaluation','The AI section needs more detail, particularly regarding the chatbot training methodology and accuracy evaluation. I recommend adding a comparison table of the NLP models used.',75.00,'normal',0,'2026-05-24 12:40:12'),(23,1,5,'committee_evaluation','The proposed UI is well thought out and appropriate. I recommend addressing accessibility requirements (WCAG) and adding support for users with special needs.',82.00,'normal',0,'2026-05-24 12:40:12'),(24,2,4,'source_code_review','The code is well-structured, but you need to add documentation comments to all major functions and write unit tests for sensitive operations such as authentication and role checking.',71.00,'normal',0,'2026-05-24 12:40:12'),(25,1,3,'final_report_review','The report is generally well-written. I recommend clarifying the system architecture section further and adding detailed ERD diagrams. Please also ensure consistent use of technical terminology across all chapters.',78.00,'important',0,'2026-05-24 19:44:29'),(26,1,4,'committee_evaluation','The AI section needs more detail, particularly regarding the chatbot training methodology and accuracy evaluation. I recommend adding a comparison table of the NLP models used.',75.00,'normal',0,'2026-05-24 19:44:29'),(27,1,5,'committee_evaluation','The proposed UI is well thought out and appropriate. I recommend addressing accessibility requirements (WCAG) and adding support for users with special needs.',82.00,'normal',0,'2026-05-24 19:44:29'),(28,2,4,'source_code_review','The code is well-structured, but you need to add documentation comments to all major functions and write unit tests for sensitive operations such as authentication and role checking.',71.00,'normal',0,'2026-05-24 19:44:29'),(29,1,3,'final_report_review','The report is generally well-written. I recommend clarifying the system architecture section further and adding detailed ERD diagrams. Please also ensure consistent use of technical terminology across all chapters.',78.00,'important',0,'2026-05-24 19:54:38'),(30,1,4,'committee_evaluation','The AI section needs more detail, particularly regarding the chatbot training methodology and accuracy evaluation. I recommend adding a comparison table of the NLP models used.',75.00,'normal',0,'2026-05-24 19:54:38'),(31,1,5,'committee_evaluation','The proposed UI is well thought out and appropriate. I recommend addressing accessibility requirements (WCAG) and adding support for users with special needs.',82.00,'normal',0,'2026-05-24 19:54:38'),(32,2,4,'source_code_review','The code is well-structured, but you need to add documentation comments to all major functions and write unit tests for sensitive operations such as authentication and role checking.',71.00,'normal',0,'2026-05-24 19:54:38'),(33,1,3,'final_report_review','The report is generally well-written. I recommend clarifying the system architecture section further and adding detailed ERD diagrams. Please also ensure consistent use of technical terminology across all chapters.',78.00,'important',0,'2026-05-24 20:13:39'),(34,1,4,'committee_evaluation','The AI section needs more detail, particularly regarding the chatbot training methodology and accuracy evaluation. I recommend adding a comparison table of the NLP models used.',75.00,'normal',0,'2026-05-24 20:13:39'),(35,1,5,'committee_evaluation','The proposed UI is well thought out and appropriate. I recommend addressing accessibility requirements (WCAG) and adding support for users with special needs.',82.00,'normal',0,'2026-05-24 20:13:39'),(36,2,4,'source_code_review','The code is well-structured, but you need to add documentation comments to all major functions and write unit tests for sensitive operations such as authentication and role checking.',71.00,'normal',0,'2026-05-24 20:13:39'),(37,1,3,'final_report_review','The report is generally well-written. I recommend clarifying the system architecture section further and adding detailed ERD diagrams. Please also ensure consistent use of technical terminology across all chapters.',78.00,'important',0,'2026-05-24 20:21:31'),(38,1,4,'committee_evaluation','The AI section needs more detail, particularly regarding the chatbot training methodology and accuracy evaluation. I recommend adding a comparison table of the NLP models used.',75.00,'normal',0,'2026-05-24 20:21:31'),(39,1,5,'committee_evaluation','The proposed UI is well thought out and appropriate. I recommend addressing accessibility requirements (WCAG) and adding support for users with special needs.',82.00,'normal',0,'2026-05-24 20:21:31'),(40,2,4,'source_code_review','The code is well-structured, but you need to add documentation comments to all major functions and write unit tests for sensitive operations such as authentication and role checking.',71.00,'normal',0,'2026-05-24 20:21:31'),(41,1,3,'final_report_review','The report is generally well-written. I recommend clarifying the system architecture section further and adding detailed ERD diagrams. Please also ensure consistent use of technical terminology across all chapters.',78.00,'important',0,'2026-05-24 22:16:42'),(42,1,4,'committee_evaluation','The AI section needs more detail, particularly regarding the chatbot training methodology and accuracy evaluation. I recommend adding a comparison table of the NLP models used.',75.00,'normal',0,'2026-05-24 22:16:42'),(43,1,5,'committee_evaluation','The proposed UI is well thought out and appropriate. I recommend addressing accessibility requirements (WCAG) and adding support for users with special needs.',82.00,'normal',0,'2026-05-24 22:16:42'),(44,2,4,'source_code_review','The code is well-structured, but you need to add documentation comments to all major functions and write unit tests for sensitive operations such as authentication and role checking.',71.00,'normal',0,'2026-05-24 22:16:42'),(45,1,3,'final_report_review','The report is generally well-written. I recommend clarifying the system architecture section further and adding detailed ERD diagrams. Please also ensure consistent use of technical terminology across all chapters.',78.00,'important',0,'2026-05-24 22:21:47'),(46,1,4,'committee_evaluation','The AI section needs more detail, particularly regarding the chatbot training methodology and accuracy evaluation. I recommend adding a comparison table of the NLP models used.',75.00,'normal',0,'2026-05-24 22:21:47'),(47,1,5,'committee_evaluation','The proposed UI is well thought out and appropriate. I recommend addressing accessibility requirements (WCAG) and adding support for users with special needs.',82.00,'normal',0,'2026-05-24 22:21:47'),(48,2,4,'source_code_review','The code is well-structured, but you need to add documentation comments to all major functions and write unit tests for sensitive operations such as authentication and role checking.',71.00,'normal',0,'2026-05-24 22:21:47');
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
) ENGINE=InnoDB AUTO_INCREMENT=73 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
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
) ENGINE=InnoDB AUTO_INCREMENT=37 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
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
  `attachment_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `attachment_mime` varchar(120) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `attachment_data` longblob,
  PRIMARY KEY (`notification_id`),
  KEY `sender_id` (`sender_id`),
  KEY `idx_notif_recipient` (`recipient_id`,`is_read`),
  KEY `idx_notif_project` (`related_project_id`),
  CONSTRAINT `notifications_ibfk_1` FOREIGN KEY (`recipient_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE,
  CONSTRAINT `notifications_ibfk_2` FOREIGN KEY (`sender_id`) REFERENCES `users` (`user_id`) ON DELETE SET NULL,
  CONSTRAINT `notifications_ibfk_3` FOREIGN KEY (`related_project_id`) REFERENCES `projects` (`project_id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=256 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `notifications`
--

LOCK TABLES `notifications` WRITE;
/*!40000 ALTER TABLE `notifications` DISABLE KEYS */;
INSERT INTO `notifications` VALUES (1,2,4,'project_reviewed','Dr. Radi Jarrar completed evaluations','Dr. Radi Jarrar completed 3 project evaluations — avg score: 89.3.','both',NULL,0,'2026-05-20 13:03:29',NULL,NULL,NULL),(2,2,NULL,'deadline_reminder','7 projects awaiting your decision','7 projects are pending coordinator review — some exceeded 48 hours.','both',NULL,1,'2026-05-20 13:03:29',NULL,NULL,NULL),(10,8,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-20 13:45:01',NULL,NULL,NULL),(11,9,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-20 13:45:01',NULL,NULL,NULL),(12,10,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-20 13:45:01',NULL,NULL,NULL),(13,8,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-20 13:45:01',NULL,NULL,NULL),(14,9,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-20 13:45:01',NULL,NULL,NULL),(15,10,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-20 13:45:01',NULL,NULL,NULL),(16,8,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-20 13:45:01',NULL,NULL,NULL),(17,9,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-20 13:45:01',NULL,NULL,NULL),(18,10,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-20 13:45:01',NULL,NULL,NULL),(19,11,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',2,0,'2026-05-20 13:45:01',NULL,NULL,NULL),(20,8,3,'feedback_received','Your project has been reviewed','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-20 13:45:01',NULL,NULL,NULL),(21,8,2,'committee_assigned','Committee discussion scheduled','Your project discussion is scheduled for February 20 at 10:00 AM.','both',1,0,'2026-05-20 13:45:01',NULL,NULL,NULL),(22,8,NULL,'deadline_reminder','Reminder: Upload source code','Please upload the source code files before February 15.','both',1,0,'2026-05-20 13:45:01',NULL,NULL,NULL),(23,3,8,'file_uploaded','Rahaf Badwan uploaded updated files','A new version of the final report has been uploaded — APMS project.','both',1,0,'2026-05-20 13:45:01',NULL,NULL,NULL),(24,3,2,'committee_assigned','New committee membership assigned','You have been assigned as a member of a new evaluation committee.','both',1,0,'2026-05-20 13:45:01',NULL,NULL,NULL),(25,3,NULL,'urgent_alert','Karim Odeh — urgent follow-up needed','Karim Odeh has not uploaded any files for two weeks.','both',3,0,'2026-05-20 13:45:01',NULL,NULL,NULL),(26,2,NULL,'file_uploaded','New project pending your review','Electronic Student Records Management System — Salma Al-Khatib.','both',2,0,'2026-05-20 13:45:01',NULL,NULL,NULL),(27,2,4,'project_reviewed','Dr. Radi Jarrar completed evaluations','Dr. Radi Jarrar completed 3 project evaluations — avg score: 89.3.','both',NULL,0,'2026-05-20 13:45:01',NULL,NULL,NULL),(28,2,NULL,'deadline_reminder','7 projects awaiting your decision','7 projects are pending coordinator review — some exceeded 48 hours.','both',NULL,1,'2026-05-20 13:45:01',NULL,NULL,NULL),(29,8,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-20 13:57:21',NULL,NULL,NULL),(30,9,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-20 13:57:21',NULL,NULL,NULL),(31,10,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-20 13:57:21',NULL,NULL,NULL),(32,8,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-20 13:57:21',NULL,NULL,NULL),(33,9,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-20 13:57:21',NULL,NULL,NULL),(34,10,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-20 13:57:21',NULL,NULL,NULL),(35,8,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-20 13:57:21',NULL,NULL,NULL),(36,9,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-20 13:57:21',NULL,NULL,NULL),(37,10,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-20 13:57:21',NULL,NULL,NULL),(38,11,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',2,0,'2026-05-20 13:57:21',NULL,NULL,NULL),(39,8,3,'feedback_received','Your project has been reviewed','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-20 13:57:21',NULL,NULL,NULL),(40,8,2,'committee_assigned','Committee discussion scheduled','Your project discussion is scheduled for February 20 at 10:00 AM.','both',1,0,'2026-05-20 13:57:21',NULL,NULL,NULL),(41,8,NULL,'deadline_reminder','Reminder: Upload source code','Please upload the source code files before February 15.','both',1,0,'2026-05-20 13:57:21',NULL,NULL,NULL),(42,3,8,'file_uploaded','Rahaf Badwan uploaded updated files','A new version of the final report has been uploaded — APMS project.','both',1,0,'2026-05-20 13:57:21',NULL,NULL,NULL),(43,3,2,'committee_assigned','New committee membership assigned','You have been assigned as a member of a new evaluation committee.','both',1,0,'2026-05-20 13:57:21',NULL,NULL,NULL),(44,3,NULL,'urgent_alert','Karim Odeh — urgent follow-up needed','Karim Odeh has not uploaded any files for two weeks.','both',3,0,'2026-05-20 13:57:21',NULL,NULL,NULL),(45,2,NULL,'file_uploaded','New project pending your review','Electronic Student Records Management System — Salma Al-Khatib.','both',2,0,'2026-05-20 13:57:21',NULL,NULL,NULL),(46,2,4,'project_reviewed','Dr. Radi Jarrar completed evaluations','Dr. Radi Jarrar completed 3 project evaluations — avg score: 89.3.','both',NULL,0,'2026-05-20 13:57:21',NULL,NULL,NULL),(47,2,NULL,'deadline_reminder','7 projects awaiting your decision','7 projects are pending coordinator review — some exceeded 48 hours.','both',NULL,1,'2026-05-20 13:57:21',NULL,NULL,NULL),(48,8,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-22 17:27:43',NULL,NULL,NULL),(49,9,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-22 17:27:43',NULL,NULL,NULL),(50,10,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-22 17:27:43',NULL,NULL,NULL),(51,8,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-22 17:27:43',NULL,NULL,NULL),(52,9,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-22 17:27:43',NULL,NULL,NULL),(53,10,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-22 17:27:43',NULL,NULL,NULL),(54,8,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-22 17:27:43',NULL,NULL,NULL),(55,9,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-22 17:27:43',NULL,NULL,NULL),(56,10,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-22 17:27:43',NULL,NULL,NULL),(57,11,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',2,0,'2026-05-22 17:27:43',NULL,NULL,NULL),(58,8,3,'feedback_received','Your project has been reviewed','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-22 17:27:43',NULL,NULL,NULL),(59,8,2,'committee_assigned','Committee discussion scheduled','Your project discussion is scheduled for February 20 at 10:00 AM.','both',1,0,'2026-05-22 17:27:43',NULL,NULL,NULL),(60,8,NULL,'deadline_reminder','Reminder: Upload source code','Please upload the source code files before February 15.','both',1,0,'2026-05-22 17:27:43',NULL,NULL,NULL),(61,3,8,'file_uploaded','Rahaf Badwan uploaded updated files','A new version of the final report has been uploaded — APMS project.','both',1,0,'2026-05-22 17:27:43',NULL,NULL,NULL),(62,3,2,'committee_assigned','New committee membership assigned','You have been assigned as a member of a new evaluation committee.','both',1,0,'2026-05-22 17:27:43',NULL,NULL,NULL),(63,3,NULL,'urgent_alert','Karim Odeh — urgent follow-up needed','Karim Odeh has not uploaded any files for two weeks.','both',3,0,'2026-05-22 17:27:43',NULL,NULL,NULL),(64,2,NULL,'file_uploaded','New project pending your review','Electronic Student Records Management System — Salma Al-Khatib.','both',2,0,'2026-05-22 17:27:43',NULL,NULL,NULL),(65,2,4,'project_reviewed','Dr. Radi Jarrar completed evaluations','Dr. Radi Jarrar completed 3 project evaluations — avg score: 89.3.','both',NULL,0,'2026-05-22 17:27:43',NULL,NULL,NULL),(66,2,NULL,'deadline_reminder','7 projects awaiting your decision','7 projects are pending coordinator review — some exceeded 48 hours.','both',NULL,1,'2026-05-22 17:27:43',NULL,NULL,NULL),(67,8,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-22 17:30:09',NULL,NULL,NULL),(68,9,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-22 17:30:09',NULL,NULL,NULL),(69,10,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-22 17:30:09',NULL,NULL,NULL),(70,8,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-22 17:30:09',NULL,NULL,NULL),(71,9,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-22 17:30:09',NULL,NULL,NULL),(72,10,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-22 17:30:09',NULL,NULL,NULL),(73,8,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-22 17:30:09',NULL,NULL,NULL),(74,9,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-22 17:30:09',NULL,NULL,NULL),(75,10,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-22 17:30:09',NULL,NULL,NULL),(76,11,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',2,0,'2026-05-22 17:30:09',NULL,NULL,NULL),(77,8,3,'feedback_received','Your project has been reviewed','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-22 17:30:09',NULL,NULL,NULL),(78,8,2,'committee_assigned','Committee discussion scheduled','Your project discussion is scheduled for February 20 at 10:00 AM.','both',1,0,'2026-05-22 17:30:09',NULL,NULL,NULL),(79,8,NULL,'deadline_reminder','Reminder: Upload source code','Please upload the source code files before February 15.','both',1,0,'2026-05-22 17:30:09',NULL,NULL,NULL),(80,3,8,'file_uploaded','Rahaf Badwan uploaded updated files','A new version of the final report has been uploaded — APMS project.','both',1,0,'2026-05-22 17:30:09',NULL,NULL,NULL),(81,3,2,'committee_assigned','New committee membership assigned','You have been assigned as a member of a new evaluation committee.','both',1,0,'2026-05-22 17:30:09',NULL,NULL,NULL),(82,3,NULL,'urgent_alert','Karim Odeh — urgent follow-up needed','Karim Odeh has not uploaded any files for two weeks.','both',3,0,'2026-05-22 17:30:09',NULL,NULL,NULL),(83,2,NULL,'file_uploaded','New project pending your review','Electronic Student Records Management System — Salma Al-Khatib.','both',2,0,'2026-05-22 17:30:09',NULL,NULL,NULL),(84,2,4,'project_reviewed','Dr. Radi Jarrar completed evaluations','Dr. Radi Jarrar completed 3 project evaluations — avg score: 89.3.','both',NULL,0,'2026-05-22 17:30:09',NULL,NULL,NULL),(85,2,NULL,'deadline_reminder','7 projects awaiting your decision','7 projects are pending coordinator review — some exceeded 48 hours.','both',NULL,1,'2026-05-22 17:30:09',NULL,NULL,NULL),(86,8,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',1,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(87,9,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',1,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(88,10,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',1,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(89,11,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',2,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(90,12,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',3,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(91,13,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',4,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(92,49,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',4,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(93,50,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',4,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(94,14,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',5,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(95,51,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',5,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(96,52,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',5,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(97,15,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',6,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(98,53,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',6,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(99,54,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',6,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(100,55,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',7,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(101,56,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',7,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(103,57,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',8,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(104,58,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',8,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(106,15,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',9,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(107,59,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',9,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(108,60,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',9,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(109,16,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',10,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(110,17,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',10,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(111,61,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',10,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(112,62,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',10,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(116,11,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',11,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(117,12,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',11,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(118,63,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',11,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(119,64,NULL,'status_changed','Project status updated','Your project status has changed to: archived','both',11,0,'2026-05-22 18:43:16',NULL,NULL,NULL),(123,8,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 12:40:12',NULL,NULL,NULL),(124,9,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 12:40:12',NULL,NULL,NULL),(125,10,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 12:40:12',NULL,NULL,NULL),(126,8,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-24 12:40:12',NULL,NULL,NULL),(127,9,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-24 12:40:12',NULL,NULL,NULL),(128,10,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-24 12:40:12',NULL,NULL,NULL),(129,8,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-24 12:40:12',NULL,NULL,NULL),(130,9,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-24 12:40:12',NULL,NULL,NULL),(131,10,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-24 12:40:12',NULL,NULL,NULL),(132,11,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',2,0,'2026-05-24 12:40:12',NULL,NULL,NULL),(133,8,3,'feedback_received','Your project has been reviewed','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 12:40:12',NULL,NULL,NULL),(134,8,2,'committee_assigned','Committee discussion scheduled','Your project discussion is scheduled for February 20 at 10:00 AM.','both',1,0,'2026-05-24 12:40:12',NULL,NULL,NULL),(135,8,NULL,'deadline_reminder','Reminder: Upload source code','Please upload the source code files before February 15.','both',1,0,'2026-05-24 12:40:12',NULL,NULL,NULL),(136,3,8,'file_uploaded','Rahaf Badwan uploaded updated files','A new version of the final report has been uploaded — APMS project.','both',1,0,'2026-05-24 12:40:12',NULL,NULL,NULL),(137,3,2,'committee_assigned','New committee membership assigned','You have been assigned as a member of a new evaluation committee.','both',1,0,'2026-05-24 12:40:12',NULL,NULL,NULL),(138,3,NULL,'urgent_alert','Karim Odeh — urgent follow-up needed','Karim Odeh has not uploaded any files for two weeks.','both',3,0,'2026-05-24 12:40:12',NULL,NULL,NULL),(139,2,NULL,'file_uploaded','New project pending your review','Electronic Student Records Management System — Salma Al-Khatib.','both',2,0,'2026-05-24 12:40:12',NULL,NULL,NULL),(140,2,4,'project_reviewed','Dr. Radi Jarrar completed evaluations','Dr. Radi Jarrar completed 3 project evaluations — avg score: 89.3.','both',NULL,0,'2026-05-24 12:40:12',NULL,NULL,NULL),(141,2,NULL,'deadline_reminder','7 projects awaiting your decision','7 projects are pending coordinator review — some exceeded 48 hours.','both',NULL,1,'2026-05-24 12:40:12',NULL,NULL,NULL),(142,8,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 19:44:29',NULL,NULL,NULL),(143,9,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 19:44:29',NULL,NULL,NULL),(144,10,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 19:44:29',NULL,NULL,NULL),(145,8,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-24 19:44:29',NULL,NULL,NULL),(146,9,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-24 19:44:29',NULL,NULL,NULL),(147,10,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-24 19:44:29',NULL,NULL,NULL),(148,8,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-24 19:44:29',NULL,NULL,NULL),(149,9,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-24 19:44:29',NULL,NULL,NULL),(150,10,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-24 19:44:29',NULL,NULL,NULL),(151,11,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',2,0,'2026-05-24 19:44:29',NULL,NULL,NULL),(152,8,3,'feedback_received','Your project has been reviewed','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 19:44:30',NULL,NULL,NULL),(153,8,2,'committee_assigned','Committee discussion scheduled','Your project discussion is scheduled for February 20 at 10:00 AM.','both',1,0,'2026-05-24 19:44:30',NULL,NULL,NULL),(154,8,NULL,'deadline_reminder','Reminder: Upload source code','Please upload the source code files before February 15.','both',1,0,'2026-05-24 19:44:30',NULL,NULL,NULL),(155,3,8,'file_uploaded','Rahaf Badwan uploaded updated files','A new version of the final report has been uploaded — APMS project.','both',1,0,'2026-05-24 19:44:30',NULL,NULL,NULL),(156,3,2,'committee_assigned','New committee membership assigned','You have been assigned as a member of a new evaluation committee.','both',1,0,'2026-05-24 19:44:30',NULL,NULL,NULL),(157,3,NULL,'urgent_alert','Karim Odeh — urgent follow-up needed','Karim Odeh has not uploaded any files for two weeks.','both',3,0,'2026-05-24 19:44:30',NULL,NULL,NULL),(158,2,NULL,'file_uploaded','New project pending your review','Electronic Student Records Management System — Salma Al-Khatib.','both',2,0,'2026-05-24 19:44:30',NULL,NULL,NULL),(159,2,4,'project_reviewed','Dr. Radi Jarrar completed evaluations','Dr. Radi Jarrar completed 3 project evaluations — avg score: 89.3.','both',NULL,0,'2026-05-24 19:44:30',NULL,NULL,NULL),(160,2,NULL,'deadline_reminder','7 projects awaiting your decision','7 projects are pending coordinator review — some exceeded 48 hours.','both',NULL,1,'2026-05-24 19:44:30',NULL,NULL,NULL),(161,8,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 19:54:38',NULL,NULL,NULL),(162,9,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 19:54:38',NULL,NULL,NULL),(163,10,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 19:54:38',NULL,NULL,NULL),(164,8,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-24 19:54:38',NULL,NULL,NULL),(165,9,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-24 19:54:38',NULL,NULL,NULL),(166,10,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-24 19:54:38',NULL,NULL,NULL),(167,8,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-24 19:54:38',NULL,NULL,NULL),(168,9,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-24 19:54:38',NULL,NULL,NULL),(169,10,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-24 19:54:38',NULL,NULL,NULL),(170,11,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',2,0,'2026-05-24 19:54:38',NULL,NULL,NULL),(171,8,3,'feedback_received','Your project has been reviewed','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 19:54:38',NULL,NULL,NULL),(172,8,2,'committee_assigned','Committee discussion scheduled','Your project discussion is scheduled for February 20 at 10:00 AM.','both',1,0,'2026-05-24 19:54:38',NULL,NULL,NULL),(173,8,NULL,'deadline_reminder','Reminder: Upload source code','Please upload the source code files before February 15.','both',1,0,'2026-05-24 19:54:38',NULL,NULL,NULL),(174,3,8,'file_uploaded','Rahaf Badwan uploaded updated files','A new version of the final report has been uploaded — APMS project.','both',1,0,'2026-05-24 19:54:38',NULL,NULL,NULL),(175,3,2,'committee_assigned','New committee membership assigned','You have been assigned as a member of a new evaluation committee.','both',1,0,'2026-05-24 19:54:38',NULL,NULL,NULL),(176,3,NULL,'urgent_alert','Karim Odeh — urgent follow-up needed','Karim Odeh has not uploaded any files for two weeks.','both',3,0,'2026-05-24 19:54:38',NULL,NULL,NULL),(177,2,NULL,'file_uploaded','New project pending your review','Electronic Student Records Management System — Salma Al-Khatib.','both',2,0,'2026-05-24 19:54:38',NULL,NULL,NULL),(178,2,4,'project_reviewed','Dr. Radi Jarrar completed evaluations','Dr. Radi Jarrar completed 3 project evaluations — avg score: 89.3.','both',NULL,0,'2026-05-24 19:54:38',NULL,NULL,NULL),(179,2,NULL,'deadline_reminder','7 projects awaiting your decision','7 projects are pending coordinator review — some exceeded 48 hours.','both',NULL,1,'2026-05-24 19:54:38',NULL,NULL,NULL),(180,8,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 20:13:39',NULL,NULL,NULL),(181,9,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 20:13:39',NULL,NULL,NULL),(182,10,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 20:13:39',NULL,NULL,NULL),(183,8,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-24 20:13:39',NULL,NULL,NULL),(184,9,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-24 20:13:39',NULL,NULL,NULL),(185,10,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-24 20:13:39',NULL,NULL,NULL),(186,8,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-24 20:13:39',NULL,NULL,NULL),(187,9,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-24 20:13:39',NULL,NULL,NULL),(188,10,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-24 20:13:39',NULL,NULL,NULL),(189,11,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',2,0,'2026-05-24 20:13:39',NULL,NULL,NULL),(190,8,3,'feedback_received','Your project has been reviewed','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 20:13:39',NULL,NULL,NULL),(191,8,2,'committee_assigned','Committee discussion scheduled','Your project discussion is scheduled for February 20 at 10:00 AM.','both',1,0,'2026-05-24 20:13:39',NULL,NULL,NULL),(192,8,NULL,'deadline_reminder','Reminder: Upload source code','Please upload the source code files before February 15.','both',1,0,'2026-05-24 20:13:39',NULL,NULL,NULL),(193,3,8,'file_uploaded','Rahaf Badwan uploaded updated files','A new version of the final report has been uploaded — APMS project.','both',1,0,'2026-05-24 20:13:39',NULL,NULL,NULL),(194,3,2,'committee_assigned','New committee membership assigned','You have been assigned as a member of a new evaluation committee.','both',1,0,'2026-05-24 20:13:39',NULL,NULL,NULL),(195,3,NULL,'urgent_alert','Karim Odeh — urgent follow-up needed','Karim Odeh has not uploaded any files for two weeks.','both',3,0,'2026-05-24 20:13:39',NULL,NULL,NULL),(196,2,NULL,'file_uploaded','New project pending your review','Electronic Student Records Management System — Salma Al-Khatib.','both',2,0,'2026-05-24 20:13:39',NULL,NULL,NULL),(197,2,4,'project_reviewed','Dr. Radi Jarrar completed evaluations','Dr. Radi Jarrar completed 3 project evaluations — avg score: 89.3.','both',NULL,0,'2026-05-24 20:13:39',NULL,NULL,NULL),(198,2,NULL,'deadline_reminder','7 projects awaiting your decision','7 projects are pending coordinator review — some exceeded 48 hours.','both',NULL,1,'2026-05-24 20:13:39',NULL,NULL,NULL),(199,8,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 20:21:31',NULL,NULL,NULL),(200,9,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 20:21:31',NULL,NULL,NULL),(201,10,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 20:21:31',NULL,NULL,NULL),(202,8,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-24 20:21:31',NULL,NULL,NULL),(203,9,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-24 20:21:31',NULL,NULL,NULL),(204,10,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-24 20:21:31',NULL,NULL,NULL),(205,8,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-24 20:21:31',NULL,NULL,NULL),(206,9,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-24 20:21:31',NULL,NULL,NULL),(207,10,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-24 20:21:31',NULL,NULL,NULL),(208,11,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',2,0,'2026-05-24 20:21:31',NULL,NULL,NULL),(209,8,3,'feedback_received','Your project has been reviewed','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 20:21:31',NULL,NULL,NULL),(210,8,2,'committee_assigned','Committee discussion scheduled','Your project discussion is scheduled for February 20 at 10:00 AM.','both',1,0,'2026-05-24 20:21:31',NULL,NULL,NULL),(211,8,NULL,'deadline_reminder','Reminder: Upload source code','Please upload the source code files before February 15.','both',1,0,'2026-05-24 20:21:31',NULL,NULL,NULL),(212,3,8,'file_uploaded','Rahaf Badwan uploaded updated files','A new version of the final report has been uploaded — APMS project.','both',1,0,'2026-05-24 20:21:31',NULL,NULL,NULL),(213,3,2,'committee_assigned','New committee membership assigned','You have been assigned as a member of a new evaluation committee.','both',1,0,'2026-05-24 20:21:31',NULL,NULL,NULL),(214,3,NULL,'urgent_alert','Karim Odeh — urgent follow-up needed','Karim Odeh has not uploaded any files for two weeks.','both',3,0,'2026-05-24 20:21:31',NULL,NULL,NULL),(215,2,NULL,'file_uploaded','New project pending your review','Electronic Student Records Management System — Salma Al-Khatib.','both',2,0,'2026-05-24 20:21:31',NULL,NULL,NULL),(216,2,4,'project_reviewed','Dr. Radi Jarrar completed evaluations','Dr. Radi Jarrar completed 3 project evaluations — avg score: 89.3.','both',NULL,0,'2026-05-24 20:21:31',NULL,NULL,NULL),(217,2,NULL,'deadline_reminder','7 projects awaiting your decision','7 projects are pending coordinator review — some exceeded 48 hours.','both',NULL,1,'2026-05-24 20:21:31',NULL,NULL,NULL),(218,8,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 22:16:42',NULL,NULL,NULL),(219,9,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 22:16:42',NULL,NULL,NULL),(220,10,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 22:16:42',NULL,NULL,NULL),(221,8,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-24 22:16:42',NULL,NULL,NULL),(222,9,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-24 22:16:42',NULL,NULL,NULL),(223,10,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-24 22:16:42',NULL,NULL,NULL),(224,8,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-24 22:16:42',NULL,NULL,NULL),(225,9,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-24 22:16:42',NULL,NULL,NULL),(226,10,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-24 22:16:42',NULL,NULL,NULL),(227,11,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',2,0,'2026-05-24 22:16:42',NULL,NULL,NULL),(228,8,3,'feedback_received','Your project has been reviewed','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 22:16:42',NULL,NULL,NULL),(229,8,2,'committee_assigned','Committee discussion scheduled','Your project discussion is scheduled for February 20 at 10:00 AM.','both',1,0,'2026-05-24 22:16:42',NULL,NULL,NULL),(230,8,NULL,'deadline_reminder','Reminder: Upload source code','Please upload the source code files before February 15.','both',1,0,'2026-05-24 22:16:42',NULL,NULL,NULL),(231,3,8,'file_uploaded','Rahaf Badwan uploaded updated files','A new version of the final report has been uploaded — APMS project.','both',1,0,'2026-05-24 22:16:42',NULL,NULL,NULL),(232,3,2,'committee_assigned','New committee membership assigned','You have been assigned as a member of a new evaluation committee.','both',1,0,'2026-05-24 22:16:42',NULL,NULL,NULL),(233,3,NULL,'urgent_alert','Karim Odeh — urgent follow-up needed','Karim Odeh has not uploaded any files for two weeks.','both',3,0,'2026-05-24 22:16:42',NULL,NULL,NULL),(234,2,NULL,'file_uploaded','New project pending your review','Electronic Student Records Management System — Salma Al-Khatib.','both',2,0,'2026-05-24 22:16:42',NULL,NULL,NULL),(235,2,4,'project_reviewed','Dr. Radi Jarrar completed evaluations','Dr. Radi Jarrar completed 3 project evaluations — avg score: 89.3.','both',NULL,0,'2026-05-24 22:16:42',NULL,NULL,NULL),(236,2,NULL,'deadline_reminder','7 projects awaiting your decision','7 projects are pending coordinator review — some exceeded 48 hours.','both',NULL,1,'2026-05-24 22:16:42',NULL,NULL,NULL),(237,8,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 22:21:47',NULL,NULL,NULL),(238,9,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 22:21:47',NULL,NULL,NULL),(239,10,3,'feedback_received','New feedback on your project','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 22:21:47',NULL,NULL,NULL),(240,8,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-24 22:21:47',NULL,NULL,NULL),(241,9,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-24 22:21:47',NULL,NULL,NULL),(242,10,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',1,0,'2026-05-24 22:21:47',NULL,NULL,NULL),(243,8,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-24 22:21:47',NULL,NULL,NULL),(244,9,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-24 22:21:47',NULL,NULL,NULL),(245,10,5,'feedback_received','New feedback on your project','Dr. Abdullah Krakeh has submitted new feedback on your project.','both',1,0,'2026-05-24 22:21:47',NULL,NULL,NULL),(246,11,4,'feedback_received','New feedback on your project','Dr. Radi Jarrar has submitted new feedback on your project.','both',2,0,'2026-05-24 22:21:47',NULL,NULL,NULL),(247,8,3,'feedback_received','Your project has been reviewed','Dr. Sobhi Ahmad has submitted new feedback on your project.','both',1,0,'2026-05-24 22:21:47',NULL,NULL,NULL),(248,8,2,'committee_assigned','Committee discussion scheduled','Your project discussion is scheduled for February 20 at 10:00 AM.','both',1,0,'2026-05-24 22:21:47',NULL,NULL,NULL),(249,8,NULL,'deadline_reminder','Reminder: Upload source code','Please upload the source code files before February 15.','both',1,0,'2026-05-24 22:21:47',NULL,NULL,NULL),(250,3,8,'file_uploaded','Rahaf Badwan uploaded updated files','A new version of the final report has been uploaded — APMS project.','both',1,0,'2026-05-24 22:21:47',NULL,NULL,NULL),(251,3,2,'committee_assigned','New committee membership assigned','You have been assigned as a member of a new evaluation committee.','both',1,0,'2026-05-24 22:21:47',NULL,NULL,NULL),(252,3,NULL,'urgent_alert','Karim Odeh — urgent follow-up needed','Karim Odeh has not uploaded any files for two weeks.','both',3,0,'2026-05-24 22:21:47',NULL,NULL,NULL),(253,2,NULL,'file_uploaded','New project pending your review','Electronic Student Records Management System — Salma Al-Khatib.','both',2,0,'2026-05-24 22:21:47',NULL,NULL,NULL),(254,2,4,'project_reviewed','Dr. Radi Jarrar completed evaluations','Dr. Radi Jarrar completed 3 project evaluations — avg score: 89.3.','both',NULL,0,'2026-05-24 22:21:47',NULL,NULL,NULL),(255,2,NULL,'deadline_reminder','7 projects awaiting your decision','7 projects are pending coordinator review — some exceeded 48 hours.','both',NULL,1,'2026-05-24 22:21:47',NULL,NULL,NULL);
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
  `workflow_status` enum('draft','sent_to_supervisor','sent_to_head','published_to_students') NOT NULL DEFAULT 'draft',
  `notes` text,
  `published_by` int DEFAULT NULL,
  `published_at` datetime DEFAULT NULL,
  `sent_by_coordinator` int DEFAULT NULL,
  `sent_to_supervisor_at` datetime DEFAULT NULL,
  `supervisor_id` int DEFAULT NULL,
  `supervisor_sent_by` int DEFAULT NULL,
  `supervisor_sent_to_head_at` datetime DEFAULT NULL,
  `head_published_by` int DEFAULT NULL,
  `head_published_at` datetime DEFAULT NULL,
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
  `component` enum('intro_report_reader','intro_supervisor','intro_discussion_member','grad_report_reader','grad_supervisor','grad_committee_member') NOT NULL,
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
) ENGINE=InnoDB AUTO_INCREMENT=205 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `project_lifecycle`
--

LOCK TABLES `project_lifecycle` WRITE;
/*!40000 ALTER TABLE `project_lifecycle` DISABLE KEYS */;
INSERT INTO `project_lifecycle` VALUES (14,1,'registration','completed','2026-01-25','2026-01-25','Project registered successfully'),(15,1,'file_submission','completed','2026-02-01','2026-02-01','Report and source code uploaded — slides still required'),(16,1,'initial_review','in_progress','2026-02-03',NULL,'Supervisor Dr. Naima is reviewing the final report; feedback expected within 48 hours'),(17,1,'supervisor_review','pending',NULL,NULL,NULL),(18,1,'committee_evaluation','pending','2026-02-20',NULL,NULL),(19,1,'final_result','pending','2026-02-28',NULL,NULL),(20,1,'archiving','pending',NULL,NULL,NULL),(21,4,'registration','completed','2025-01-15','2025-01-15',NULL),(22,4,'file_submission','completed','2025-02-01','2025-02-01',NULL),(23,4,'initial_review','completed','2025-02-05','2025-02-05',NULL),(24,4,'committee_evaluation','completed','2025-02-21','2025-02-21',NULL),(25,4,'final_result','completed','2025-02-28','2025-02-28',NULL),(26,4,'archiving','completed','2025-03-01','2025-03-01',NULL),(144,115,'registration','completed','2026-05-25','2026-05-25','Seed registration completed'),(145,116,'registration','completed','2026-05-25','2026-05-25','Seed registration completed'),(146,117,'registration','completed','2026-05-25','2026-05-25','Seed registration completed'),(147,118,'registration','completed','2026-05-25','2026-05-25','Seed registration completed'),(148,119,'registration','completed','2026-05-25','2026-05-25','Seed registration completed'),(149,120,'registration','completed','2026-05-25','2026-05-25','Seed registration completed'),(150,121,'registration','completed','2026-05-25','2026-05-25','Seed registration completed'),(151,122,'registration','completed','2026-05-25','2026-05-25','Seed registration completed'),(152,123,'registration','completed','2026-05-25','2026-05-25','Seed registration completed'),(153,124,'registration','completed','2026-05-25','2026-05-25','Seed registration completed'),(159,115,'file_submission','completed','2026-05-25','2026-05-25','Seed file submission completed'),(160,116,'file_submission','completed','2026-05-25','2026-05-25','Seed file submission completed'),(161,117,'file_submission','completed','2026-05-25','2026-05-25','Seed file submission completed'),(162,118,'file_submission','completed','2026-05-25','2026-05-25','Seed file submission completed'),(163,119,'file_submission','completed','2026-05-25','2026-05-25','Seed file submission completed'),(164,120,'file_submission','completed','2026-05-25','2026-05-25','Seed file submission completed'),(165,121,'file_submission','completed','2026-05-25','2026-05-25','Seed file submission completed'),(166,122,'file_submission','completed','2026-05-25','2026-05-25','Seed file submission completed'),(167,123,'file_submission','completed','2026-05-25','2026-05-25','Seed file submission completed'),(168,124,'file_submission','completed','2026-05-25','2026-05-25','Seed file submission completed'),(174,115,'committee_evaluation','pending','2026-05-25',NULL,'Ready for committee generation'),(175,116,'committee_evaluation','pending','2026-05-25',NULL,'Ready for committee generation'),(176,117,'committee_evaluation','pending','2026-05-25',NULL,'Ready for committee generation'),(177,118,'committee_evaluation','pending','2026-05-25',NULL,'Ready for committee generation'),(178,119,'committee_evaluation','pending','2026-05-25',NULL,'Ready for committee generation'),(179,120,'committee_evaluation','pending','2026-05-25',NULL,'Ready for committee generation'),(180,121,'committee_evaluation','pending','2026-05-25',NULL,'Ready for committee generation'),(181,122,'committee_evaluation','pending','2026-05-25',NULL,'Ready for committee generation'),(182,123,'committee_evaluation','pending','2026-05-25',NULL,'Ready for committee generation'),(183,124,'committee_evaluation','pending','2026-05-25',NULL,'Ready for committee generation');
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
) ENGINE=InnoDB AUTO_INCREMENT=265 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `project_members`
--

LOCK TABLES `project_members` WRITE;
/*!40000 ALTER TABLE `project_members` DISABLE KEYS */;
INSERT INTO `project_members` VALUES (19,4,11,1,'2026-05-20 13:03:32'),(20,4,12,0,'2026-05-20 13:03:32'),(21,5,13,1,'2026-05-20 13:03:32'),(22,5,14,0,'2026-05-20 13:03:32'),(23,6,15,1,'2026-05-20 13:03:32'),(24,6,16,0,'2026-05-20 13:03:32'),(25,7,17,1,'2026-05-20 13:03:32'),(26,7,18,0,'2026-05-20 13:03:32'),(27,8,19,1,'2026-05-20 13:03:32'),(28,8,20,0,'2026-05-20 13:03:32'),(29,9,21,1,'2026-05-20 13:03:32'),(30,9,22,0,'2026-05-20 13:03:32'),(31,10,23,1,'2026-05-20 13:03:32'),(32,10,24,0,'2026-05-20 13:03:32'),(33,11,25,1,'2026-05-20 13:03:32'),(34,11,26,0,'2026-05-20 13:03:32'),(35,1,2,0,'2026-05-20 13:45:01'),(36,1,1,1,'2026-05-20 13:45:01'),(37,1,3,0,'2026-05-20 13:45:01'),(38,2,4,1,'2026-05-20 13:45:01'),(39,3,5,1,'2026-05-20 13:45:01'),(40,4,6,1,'2026-05-20 13:45:01'),(41,5,7,1,'2026-05-20 13:45:01'),(42,6,8,1,'2026-05-20 13:45:01'),(43,9,8,0,'2026-05-20 13:45:01'),(44,10,9,1,'2026-05-20 13:45:02'),(45,10,10,0,'2026-05-20 13:45:02'),(46,11,4,1,'2026-05-20 13:45:02'),(47,11,5,0,'2026-05-20 13:45:02'),(48,12,6,1,'2026-05-20 13:45:02'),(49,12,7,0,'2026-05-20 13:45:02'),(50,12,8,0,'2026-05-20 13:45:02'),(215,115,172,1,'2026-05-24 22:16:43'),(216,115,173,0,'2026-05-24 22:16:43'),(217,115,174,0,'2026-05-24 22:16:43'),(218,116,175,1,'2026-05-24 22:16:43'),(219,116,176,0,'2026-05-24 22:16:43'),(220,116,177,0,'2026-05-24 22:16:43'),(221,117,178,1,'2026-05-24 22:16:43'),(222,117,179,0,'2026-05-24 22:16:43'),(223,117,180,0,'2026-05-24 22:16:43'),(224,118,181,1,'2026-05-24 22:16:43'),(225,118,182,0,'2026-05-24 22:16:43'),(226,118,183,0,'2026-05-24 22:16:43'),(227,119,184,1,'2026-05-24 22:16:43'),(228,119,185,0,'2026-05-24 22:16:43'),(229,119,186,0,'2026-05-24 22:16:43'),(230,120,187,1,'2026-05-24 22:16:43'),(231,120,188,0,'2026-05-24 22:16:43'),(232,120,189,0,'2026-05-24 22:16:43'),(233,121,190,1,'2026-05-24 22:16:43'),(234,121,191,0,'2026-05-24 22:16:43'),(235,121,192,0,'2026-05-24 22:16:43'),(236,122,193,1,'2026-05-24 22:16:43'),(237,122,194,0,'2026-05-24 22:16:43'),(238,122,195,0,'2026-05-24 22:16:43'),(239,123,196,1,'2026-05-24 22:16:43'),(240,123,197,0,'2026-05-24 22:16:43'),(241,123,198,0,'2026-05-24 22:16:43'),(242,124,199,1,'2026-05-24 22:16:43'),(243,124,200,0,'2026-05-24 22:16:43'),(244,124,201,0,'2026-05-24 22:16:43');
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
) ENGINE=InnoDB AUTO_INCREMENT=85 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
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
  `files_count` int NOT NULL DEFAULT '0',
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
) ENGINE=InnoDB AUTO_INCREMENT=130 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `projects`
--

LOCK TABLES `projects` WRITE;
/*!40000 ALTER TABLE `projects` DISABLE KEYS */;
INSERT INTO `projects` VALUES (1,NULL,'Advanced AI Decision System',NULL,NULL,NULL,'ai',5,4,NULL,NULL,NULL,'archived','2026-05-20',NULL,NULL,NULL,0,'2026-05-20 13:03:29','2026-05-22 18:43:16'),(2,NULL,'Enterprise Web Platform',NULL,NULL,NULL,'web',5,5,NULL,NULL,NULL,'archived','2026-05-20',NULL,NULL,NULL,0,'2026-05-20 13:03:29','2026-05-22 18:43:16'),(3,NULL,'Cyber Security Audit Platform',NULL,NULL,NULL,'security',5,7,NULL,NULL,NULL,'archived','2026-05-20',NULL,NULL,NULL,0,'2026-05-20 13:03:29','2026-05-22 18:43:16'),(4,NULL,'Smart Clinic Management Platform',NULL,NULL,NULL,'web',5,5,NULL,NULL,NULL,'archived','2026-05-20',NULL,NULL,NULL,0,'2026-05-20 13:03:32','2026-05-22 18:43:16'),(5,NULL,'AI Resume Screening System',NULL,NULL,NULL,'ai',5,4,NULL,NULL,NULL,'archived','2026-05-20',NULL,NULL,NULL,0,'2026-05-20 13:03:32','2026-05-22 18:43:16'),(6,NULL,'Secure Campus Access Control',NULL,NULL,NULL,'security',5,7,NULL,NULL,NULL,'archived','2026-05-20',NULL,NULL,NULL,0,'2026-05-20 13:03:32','2026-05-22 18:43:16'),(7,NULL,'Mobile Pharmacy Assistant',NULL,NULL,NULL,'mobile',5,5,NULL,NULL,NULL,'archived','2026-05-20',NULL,NULL,NULL,0,'2026-05-20 13:03:32','2026-05-22 18:43:16'),(8,NULL,'Intelligent Library Recommender',NULL,NULL,NULL,'ai',5,4,NULL,NULL,NULL,'archived','2026-05-20',NULL,NULL,NULL,0,'2026-05-20 13:03:32','2026-05-22 18:43:16'),(9,NULL,'Cloud Attendance Tracker',NULL,NULL,NULL,'web',5,3,NULL,NULL,NULL,'archived','2026-05-20',NULL,NULL,NULL,0,'2026-05-20 13:03:32','2026-05-22 18:43:16'),(10,NULL,'Database Performance Analyzer',NULL,NULL,NULL,'databases',5,6,NULL,NULL,NULL,'archived','2026-05-20',NULL,NULL,NULL,0,'2026-05-20 13:03:32','2026-05-22 18:43:16'),(11,NULL,'Smart Graduation Project Marketplace',NULL,NULL,NULL,'web',5,3,NULL,NULL,NULL,'archived','2026-05-20',NULL,NULL,NULL,0,'2026-05-20 13:03:32','2026-05-22 18:43:16'),(12,NULL,'Smart Invoice',NULL,NULL,NULL,'ai',2,3,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,82.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(13,NULL,'Kitchen Station Management System',NULL,NULL,NULL,'web',2,4,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,79.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(14,NULL,'DreamsJob Recruitment Platform',NULL,NULL,NULL,'web',2,5,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,85.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(15,NULL,'YallaRehla Travel App',NULL,NULL,NULL,'mobile',2,6,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,88.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(16,NULL,'StudentHub',NULL,NULL,NULL,'web',2,7,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,76.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(17,NULL,'Wasselha Delivery System',NULL,NULL,NULL,'mobile',2,3,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,83.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(18,NULL,'Home Sweet Home Real Estate',NULL,NULL,NULL,'web',2,4,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,80.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(19,NULL,'Birzeit University Insurance System',NULL,NULL,NULL,'web',1,5,NULL,NULL,NULL,'draft','2024-02-01',NULL,NULL,91.00,1,'2026-05-20 13:03:33','2026-05-24 20:20:29'),(20,NULL,'Sal7ly Maintenance App',NULL,NULL,NULL,'mobile',1,6,NULL,NULL,NULL,'draft','2024-02-01',NULL,NULL,78.00,1,'2026-05-20 13:03:33','2026-05-24 20:20:29'),(21,NULL,'Monitoring World News System',NULL,NULL,NULL,'web',1,7,NULL,NULL,NULL,'draft','2024-02-01',NULL,NULL,74.00,1,'2026-05-20 13:03:33','2026-05-24 20:20:29'),(22,NULL,'Prediction of Anti-Cancer Peptide ACP-XG',NULL,NULL,NULL,'ai',2,3,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,94.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(23,NULL,'FitScoop Fitness Platform',NULL,NULL,NULL,'mobile',2,4,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,81.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(24,NULL,'Wedding Planning System',NULL,NULL,NULL,'web',2,5,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,77.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(25,NULL,'PharmaApp Pharmacy Management',NULL,NULL,NULL,'mobile',2,6,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,86.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(26,NULL,'Student Digital Guide',NULL,NULL,NULL,'web',2,7,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,80.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(27,NULL,'Palestine Charity Platform',NULL,NULL,NULL,'web',2,3,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,75.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(28,NULL,'Gamified Trip Planner App',NULL,NULL,NULL,'mobile',2,4,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,89.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(29,NULL,'TechSpotter Tech News Platform',NULL,NULL,NULL,'web',2,5,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,78.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(30,NULL,'Multi-Environment Video Game',NULL,NULL,NULL,'other',2,6,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,83.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(31,NULL,'Birzeit Library Chatbot',NULL,NULL,NULL,'ai',2,7,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,92.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(32,NULL,'Policy Peek Policy Analyzer',NULL,NULL,NULL,'ai',2,3,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,87.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(33,NULL,'LifeActive Health Tracker',NULL,NULL,NULL,'mobile',2,4,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,84.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(34,NULL,'Tronix Electronics Web Application',NULL,NULL,NULL,'web',2,5,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,79.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(35,NULL,'Smart School Portal',NULL,NULL,NULL,'web',2,6,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,88.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(36,NULL,'GoHelp Volunteer Platform',NULL,NULL,NULL,'web',2,7,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,76.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(37,NULL,'KhatClarifier AI Writing Tool',NULL,NULL,NULL,'ai',2,3,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,90.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(38,NULL,'ConvoConvert Communication Tool',NULL,NULL,NULL,'ai',2,4,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,85.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(39,NULL,'Wasselni Transportation App',NULL,NULL,NULL,'mobile',2,5,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,82.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(40,NULL,'Ackerra Fitness Platform',NULL,NULL,NULL,'mobile',2,6,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,87.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(41,NULL,'Darak Real Estate Marketplace',NULL,NULL,NULL,'web',2,7,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,83.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(42,NULL,'Flora Palestine Plant Guide',NULL,NULL,NULL,'mobile',2,3,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,81.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(43,NULL,'Max Scheduling System',NULL,NULL,NULL,'web',2,4,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,77.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(44,NULL,'PayWithPalKoin Payment System',NULL,NULL,NULL,'web',2,5,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,86.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(45,NULL,'Nomad Travel Companion App',NULL,NULL,NULL,'mobile',2,6,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,84.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(46,NULL,'CarPal Car Sharing App',NULL,NULL,NULL,'mobile',2,7,NULL,NULL,NULL,'draft','2025-02-01',NULL,NULL,88.00,1,'2026-05-20 13:03:33','2026-05-24 12:40:13'),(47,NULL,'E-Voting System Using Blockchain',NULL,NULL,NULL,'security',1,3,NULL,NULL,NULL,'draft','2024-02-01',NULL,NULL,93.00,1,'2026-05-20 13:03:33','2026-05-24 20:20:29'),(48,NULL,'Nossrah Arabic Learning App',NULL,NULL,NULL,'mobile',1,4,NULL,NULL,NULL,'draft','2024-02-01',NULL,NULL,80.00,1,'2026-05-20 13:03:33','2026-05-24 20:20:29'),(49,NULL,'Wanderlust in Palestine Travel App',NULL,NULL,NULL,'web',1,5,NULL,NULL,NULL,'draft','2024-02-01',NULL,NULL,85.00,1,'2026-05-20 13:03:33','2026-05-24 20:20:29'),(50,NULL,'Medica Healthcare App',NULL,NULL,NULL,'mobile',1,6,NULL,NULL,NULL,'draft','2024-02-01',NULL,NULL,82.00,1,'2026-05-20 13:03:33','2026-05-24 20:20:29'),(51,NULL,'BZU Note Share App',NULL,NULL,NULL,'mobile',1,7,NULL,NULL,NULL,'draft','2024-02-01',NULL,NULL,79.00,1,'2026-05-20 13:03:33','2026-05-24 20:20:29'),(52,NULL,'Plestia Events Platform',NULL,NULL,NULL,'web',1,3,NULL,NULL,NULL,'draft','2024-02-01',NULL,NULL,83.00,1,'2026-05-20 13:03:33','2026-05-24 20:20:29'),(53,NULL,'Baby Voice Identification App',NULL,NULL,NULL,'ai',1,4,NULL,NULL,NULL,'draft','2024-02-01',NULL,NULL,88.00,1,'2026-05-20 13:03:33','2026-05-24 20:20:29'),(54,NULL,'Traffic Light Synchronization Optimizer',NULL,NULL,NULL,'ai',1,5,NULL,NULL,NULL,'draft','2024-02-01',NULL,NULL,91.00,1,'2026-05-20 13:03:33','2026-05-24 20:20:29'),(55,NULL,'CampusConnect University Network',NULL,NULL,NULL,'web',1,6,NULL,NULL,NULL,'draft','2024-02-01',NULL,NULL,86.00,1,'2026-05-20 13:03:33','2026-05-24 20:20:29'),(56,NULL,'Committee Demo AI Project 01',NULL,NULL,NULL,'ai',5,18,NULL,NULL,NULL,'archived','2026-05-20',NULL,NULL,NULL,0,'2026-05-20 13:03:34','2026-05-22 18:43:16'),(57,NULL,'Committee Demo AI Project 02',NULL,NULL,NULL,'ai',5,18,NULL,NULL,NULL,'archived','2026-05-20',NULL,NULL,NULL,0,'2026-05-20 13:03:34','2026-05-22 18:43:16'),(58,NULL,'Committee Demo Web Project 01',NULL,NULL,NULL,'web',5,2,NULL,NULL,NULL,'archived','2026-05-20',NULL,NULL,NULL,0,'2026-05-20 13:03:34','2026-05-22 18:43:16'),(59,NULL,'Committee Demo Web Project 02',NULL,NULL,NULL,'web',5,2,NULL,NULL,NULL,'archived','2026-05-20',NULL,NULL,NULL,0,'2026-05-20 13:03:34','2026-05-22 18:43:16'),(60,NULL,'Committee Demo SE Project 01',NULL,NULL,NULL,'software_engineering',5,1,NULL,NULL,NULL,'archived','2026-05-20',NULL,NULL,NULL,0,'2026-05-20 13:03:34','2026-05-22 18:43:16'),(61,NULL,'Committee Demo SE Project 02',NULL,NULL,NULL,'software_engineering',5,1,NULL,NULL,NULL,'archived','2026-05-20',NULL,NULL,NULL,0,'2026-05-20 13:03:34','2026-05-22 18:43:16'),(62,NULL,'Committee Demo Security Project 01',NULL,NULL,NULL,'security',5,7,NULL,NULL,NULL,'archived','2026-05-20',NULL,NULL,NULL,0,'2026-05-20 13:03:34','2026-05-22 18:43:16'),(63,NULL,'Committee Demo Security Project 02',NULL,NULL,NULL,'security',5,7,NULL,NULL,NULL,'archived','2026-05-20',NULL,NULL,NULL,0,'2026-05-20 13:03:34','2026-05-22 18:43:16'),(64,NULL,'Committee Demo Database Project 01',NULL,NULL,NULL,'databases',5,5,NULL,NULL,NULL,'archived','2026-05-20',NULL,NULL,NULL,0,'2026-05-20 13:03:34','2026-05-22 18:43:16'),(65,NULL,'Committee Demo Database Project 02',NULL,NULL,NULL,'databases',5,5,NULL,NULL,NULL,'archived','2026-05-20',NULL,NULL,NULL,0,'2026-05-20 13:03:34','2026-05-22 18:43:16'),(66,NULL,'Committee Demo Mobile Project 01',NULL,NULL,NULL,'mobile',5,6,NULL,NULL,NULL,'archived','2026-05-20',NULL,NULL,NULL,0,'2026-05-20 13:03:34','2026-05-22 18:43:16'),(67,NULL,'Committee Demo Mobile Project 02',NULL,NULL,NULL,'mobile',5,6,NULL,NULL,NULL,'archived','2026-05-20',NULL,NULL,NULL,0,'2026-05-20 13:03:34','2026-05-22 18:43:16'),(71,NULL,'Smart Invoice',NULL,NULL,NULL,'ai',2,3,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,82.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(72,NULL,'Kitchen Station Management System',NULL,NULL,NULL,'web',2,4,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,79.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(73,NULL,'DreamsJob Recruitment Platform',NULL,NULL,NULL,'web',2,5,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,85.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(74,NULL,'YallaRehla Travel App',NULL,NULL,NULL,'mobile',2,6,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,88.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(75,NULL,'StudentHub',NULL,NULL,NULL,'web',2,7,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,76.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(76,NULL,'Wasselha Delivery System',NULL,NULL,NULL,'mobile',2,3,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,83.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(77,NULL,'Home Sweet Home Real Estate',NULL,NULL,NULL,'web',2,4,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,80.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(78,NULL,'Birzeit University Insurance System',NULL,NULL,NULL,'web',1,5,NULL,NULL,NULL,'archived','2024-02-01',NULL,NULL,91.00,1,'2026-05-20 13:45:27','2026-05-24 20:20:29'),(79,NULL,'Sal7ly Maintenance App',NULL,NULL,NULL,'mobile',1,6,NULL,NULL,NULL,'archived','2024-02-01',NULL,NULL,78.00,1,'2026-05-20 13:45:27','2026-05-24 20:20:29'),(80,NULL,'Monitoring World News System',NULL,NULL,NULL,'web',1,7,NULL,NULL,NULL,'archived','2024-02-01',NULL,NULL,74.00,1,'2026-05-20 13:45:27','2026-05-24 20:20:29'),(81,NULL,'Prediction of Anti-Cancer Peptide ACP-XG',NULL,NULL,NULL,'ai',2,3,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,94.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(82,NULL,'FitScoop Fitness Platform',NULL,NULL,NULL,'mobile',2,4,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,81.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(83,NULL,'Wedding Planning System',NULL,NULL,NULL,'web',2,5,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,77.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(84,NULL,'PharmaApp Pharmacy Management',NULL,NULL,NULL,'mobile',2,6,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,86.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(85,NULL,'Student Digital Guide',NULL,NULL,NULL,'web',2,7,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,80.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(86,NULL,'Palestine Charity Platform',NULL,NULL,NULL,'web',2,3,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,75.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(87,NULL,'Gamified Trip Planner App',NULL,NULL,NULL,'mobile',2,4,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,89.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(88,NULL,'TechSpotter Tech News Platform',NULL,NULL,NULL,'web',2,5,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,78.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(89,NULL,'Multi-Environment Video Game',NULL,NULL,NULL,'other',2,6,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,83.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(90,NULL,'Birzeit Library Chatbot',NULL,NULL,NULL,'ai',2,7,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,92.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(91,NULL,'Policy Peek Policy Analyzer',NULL,NULL,NULL,'ai',2,3,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,87.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(92,NULL,'LifeActive Health Tracker',NULL,NULL,NULL,'mobile',2,4,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,84.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(93,NULL,'Tronix Electronics Web Application',NULL,NULL,NULL,'web',2,5,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,79.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(94,NULL,'Smart School Portal',NULL,NULL,NULL,'web',2,6,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,88.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(95,NULL,'GoHelp Volunteer Platform',NULL,NULL,NULL,'web',2,7,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,76.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(96,NULL,'KhatClarifier AI Writing Tool',NULL,NULL,NULL,'ai',2,3,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,90.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(97,NULL,'ConvoConvert Communication Tool',NULL,NULL,NULL,'ai',2,4,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,85.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(98,NULL,'Wasselni Transportation App',NULL,NULL,NULL,'mobile',2,5,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,82.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(99,NULL,'Ackerra Fitness Platform',NULL,NULL,NULL,'mobile',2,6,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,87.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(100,NULL,'Darak Real Estate Marketplace',NULL,NULL,NULL,'web',2,7,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,83.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(101,NULL,'Flora Palestine Plant Guide',NULL,NULL,NULL,'mobile',2,3,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,81.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(102,NULL,'Max Scheduling System',NULL,NULL,NULL,'web',2,4,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,77.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(103,NULL,'PayWithPalKoin Payment System',NULL,NULL,NULL,'web',2,5,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,86.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(104,NULL,'Nomad Travel Companion App',NULL,NULL,NULL,'mobile',2,6,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,84.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(105,NULL,'CarPal Car Sharing App',NULL,NULL,NULL,'mobile',2,7,NULL,NULL,NULL,'archived','2025-02-01',NULL,NULL,88.00,1,'2026-05-20 13:45:27','2026-05-24 12:40:13'),(106,NULL,'E-Voting System Using Blockchain',NULL,NULL,NULL,'security',1,3,NULL,NULL,NULL,'archived','2024-02-01',NULL,NULL,93.00,1,'2026-05-20 13:45:27','2026-05-24 20:20:29'),(107,NULL,'Nossrah Arabic Learning App',NULL,NULL,NULL,'mobile',1,4,NULL,NULL,NULL,'archived','2024-02-01',NULL,NULL,80.00,1,'2026-05-20 13:45:27','2026-05-24 20:20:29'),(108,NULL,'Wanderlust in Palestine Travel App',NULL,NULL,NULL,'web',1,5,NULL,NULL,NULL,'archived','2024-02-01',NULL,NULL,85.00,1,'2026-05-20 13:45:27','2026-05-24 20:20:29'),(109,NULL,'Medica Healthcare App',NULL,NULL,NULL,'mobile',1,6,NULL,NULL,NULL,'archived','2024-02-01',NULL,NULL,82.00,1,'2026-05-20 13:45:27','2026-05-24 20:20:29'),(110,NULL,'BZU Note Share App',NULL,NULL,NULL,'mobile',1,7,NULL,NULL,NULL,'archived','2024-02-01',NULL,NULL,79.00,1,'2026-05-20 13:45:27','2026-05-24 20:20:29'),(111,NULL,'Plestia Events Platform',NULL,NULL,NULL,'web',1,3,NULL,NULL,NULL,'archived','2024-02-01',NULL,NULL,83.00,1,'2026-05-20 13:45:27','2026-05-24 20:20:29'),(112,NULL,'Baby Voice Identification App',NULL,NULL,NULL,'ai',1,4,NULL,NULL,NULL,'archived','2024-02-01',NULL,NULL,88.00,1,'2026-05-20 13:45:27','2026-05-24 20:20:29'),(113,NULL,'Traffic Light Synchronization Optimizer',NULL,NULL,NULL,'ai',1,5,NULL,NULL,NULL,'archived','2024-02-01',NULL,NULL,91.00,1,'2026-05-20 13:45:27','2026-05-24 20:20:29'),(114,NULL,'CampusConnect University Network',NULL,NULL,NULL,'web',1,6,NULL,NULL,NULL,'archived','2024-02-01',NULL,NULL,86.00,1,'2026-05-20 13:45:27','2026-05-24 20:20:29'),(115,NULL,'COMP4300 Graduation Project 01 - Web Archive System','COMP4300 Graduation Project 01 - Web Archive System','Seed graduation project group for COMP4300 Graduation Project 01 - Web Archive System','COMP4300, graduation project, seed data','web',5,3,NULL,NULL,NULL,'submitted','2026-05-25',NULL,NULL,NULL,0,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(116,NULL,'COMP4300 Graduation Project 02 - AI Advising Assistant','COMP4300 Graduation Project 02 - AI Advising Assistant','Seed graduation project group for COMP4300 Graduation Project 02 - AI Advising Assistant','COMP4300, graduation project, seed data','ai',5,4,NULL,NULL,NULL,'submitted','2026-05-25',NULL,NULL,NULL,0,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(117,NULL,'COMP4300 Graduation Project 03 - Mobile Campus App','COMP4300 Graduation Project 03 - Mobile Campus App','Seed graduation project group for COMP4300 Graduation Project 03 - Mobile Campus App','COMP4300, graduation project, seed data','mobile',5,5,NULL,NULL,NULL,'submitted','2026-05-25',NULL,NULL,NULL,0,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(118,NULL,'COMP4300 Graduation Project 04 - Secure File Portal','COMP4300 Graduation Project 04 - Secure File Portal','Seed graduation project group for COMP4300 Graduation Project 04 - Secure File Portal','COMP4300, graduation project, seed data','security',5,6,NULL,NULL,NULL,'submitted','2026-05-25',NULL,NULL,NULL,0,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(119,NULL,'COMP4300 Graduation Project 05 - Database Reporting System','COMP4300 Graduation Project 05 - Database Reporting System','Seed graduation project group for COMP4300 Graduation Project 05 - Database Reporting System','COMP4300, graduation project, seed data','databases',5,7,NULL,NULL,NULL,'submitted','2026-05-25',NULL,NULL,NULL,0,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(120,NULL,'COMP4300 Graduation Project 06 - Software QA Platform','COMP4300 Graduation Project 06 - Software QA Platform','Seed graduation project group for COMP4300 Graduation Project 06 - Software QA Platform','COMP4300, graduation project, seed data','software_engineering',5,8,NULL,NULL,NULL,'submitted','2026-05-25',NULL,NULL,NULL,0,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(121,NULL,'COMP4300 Graduation Project 07 - Smart Attendance System','COMP4300 Graduation Project 07 - Smart Attendance System','Seed graduation project group for COMP4300 Graduation Project 07 - Smart Attendance System','COMP4300, graduation project, seed data','web',5,9,NULL,NULL,NULL,'submitted','2026-05-25',NULL,NULL,NULL,0,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(122,NULL,'COMP4300 Graduation Project 08 - IoT Monitoring Dashboard','COMP4300 Graduation Project 08 - IoT Monitoring Dashboard','Seed graduation project group for COMP4300 Graduation Project 08 - IoT Monitoring Dashboard','COMP4300, graduation project, seed data','software_engineering',5,10,NULL,NULL,NULL,'submitted','2026-05-25',NULL,NULL,NULL,0,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(123,NULL,'COMP4300 Graduation Project 09 - Cyber Risk Analyzer','COMP4300 Graduation Project 09 - Cyber Risk Analyzer','Seed graduation project group for COMP4300 Graduation Project 09 - Cyber Risk Analyzer','COMP4300, graduation project, seed data','security',5,11,NULL,NULL,NULL,'submitted','2026-05-25',NULL,NULL,NULL,0,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(124,NULL,'COMP4300 Graduation Project 10 - Academic Chatbot System','COMP4300 Graduation Project 10 - Academic Chatbot System','Seed graduation project group for COMP4300 Graduation Project 10 - Academic Chatbot System','COMP4300, graduation project, seed data','ai',5,13,NULL,NULL,NULL,'submitted','2026-05-25',NULL,NULL,NULL,0,'2026-05-24 22:16:43','2026-05-24 22:16:43');
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
-- Table structure for table `section_report_readers`
--

DROP TABLE IF EXISTS `section_report_readers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `section_report_readers` (
  `id` int NOT NULL AUTO_INCREMENT,
  `section_id` int NOT NULL,
  `faculty_id` int NOT NULL,
  `reader_order` tinyint NOT NULL,
  `assigned_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_section_reader_order` (`section_id`,`reader_order`),
  UNIQUE KEY `uq_section_reader_faculty` (`section_id`,`faculty_id`),
  KEY `faculty_id` (`faculty_id`),
  CONSTRAINT `section_report_readers_ibfk_1` FOREIGN KEY (`section_id`) REFERENCES `student_distribution_sections` (`section_id`) ON DELETE CASCADE,
  CONSTRAINT `section_report_readers_ibfk_2` FOREIGN KEY (`faculty_id`) REFERENCES `faculty` (`faculty_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `section_report_readers`
--

LOCK TABLES `section_report_readers` WRITE;
/*!40000 ALTER TABLE `section_report_readers` DISABLE KEYS */;
/*!40000 ALTER TABLE `section_report_readers` ENABLE KEYS */;
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
  UNIQUE KEY `uq_section_students_student` (`student_id`),
  CONSTRAINT `section_students_ibfk_1` FOREIGN KEY (`section_id`) REFERENCES `student_distribution_sections` (`section_id`) ON DELETE CASCADE,
  CONSTRAINT `section_students_ibfk_2` FOREIGN KEY (`student_id`) REFERENCES `students` (`student_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=33 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `section_students`
--

LOCK TABLES `section_students` WRITE;
/*!40000 ALTER TABLE `section_students` DISABLE KEYS */;
INSERT INTO `section_students` VALUES (1,4,142,'2026-05-24 22:16:43'),(2,4,143,'2026-05-24 22:16:43'),(3,4,144,'2026-05-24 22:16:43'),(4,5,145,'2026-05-24 22:16:43'),(5,5,146,'2026-05-24 22:16:43'),(6,5,147,'2026-05-24 22:16:43'),(7,6,148,'2026-05-24 22:16:43'),(8,6,149,'2026-05-24 22:16:43'),(9,6,150,'2026-05-24 22:16:43'),(10,7,151,'2026-05-24 22:16:43'),(11,7,152,'2026-05-24 22:16:43'),(12,7,153,'2026-05-24 22:16:43'),(13,8,154,'2026-05-24 22:16:43'),(14,8,155,'2026-05-24 22:16:43'),(15,8,156,'2026-05-24 22:16:43'),(16,9,157,'2026-05-24 22:16:43'),(17,9,158,'2026-05-24 22:16:43'),(18,9,159,'2026-05-24 22:16:43'),(19,10,160,'2026-05-24 22:16:43'),(20,10,161,'2026-05-24 22:16:43'),(21,10,162,'2026-05-24 22:16:43'),(22,11,163,'2026-05-24 22:16:43'),(23,11,164,'2026-05-24 22:16:43'),(24,11,165,'2026-05-24 22:16:43'),(25,12,166,'2026-05-24 22:16:43'),(26,12,167,'2026-05-24 22:16:43'),(27,12,168,'2026-05-24 22:16:43'),(28,13,169,'2026-05-24 22:16:43'),(29,13,170,'2026-05-24 22:16:43'),(30,13,171,'2026-05-24 22:16:43');
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
) ENGINE=InnoDB AUTO_INCREMENT=65 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
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
) ENGINE=InnoDB AUTO_INCREMENT=119 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Student results in COMP4200 — shared between coordinator and head';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `student_course_results`
--

LOCK TABLES `student_course_results` WRITE;
/*!40000 ALTER TABLE `student_course_results` DISABLE KEYS */;
INSERT INTO `student_course_results` VALUES (1,1,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(2,2,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(3,3,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(4,4,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(5,5,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(6,6,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(7,7,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(8,8,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(9,9,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(10,10,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(16,11,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(17,12,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(18,13,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(19,14,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(20,15,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(21,16,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(22,17,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(23,18,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(24,19,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(25,20,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(26,21,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(27,22,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(28,23,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(29,24,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(30,25,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(31,26,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(32,27,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(33,28,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(34,29,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(35,30,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(36,31,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(37,32,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(38,33,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(39,34,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-20 13:45:02','2026-05-20 13:45:02'),(56,142,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(57,143,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(58,144,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(59,145,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(60,146,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(61,147,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(62,148,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(63,149,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(64,150,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(65,151,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(66,152,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(67,153,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(68,154,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(69,155,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(70,156,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(71,157,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(72,158,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(73,159,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(74,160,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(75,161,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(76,162,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(77,163,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(78,164,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(79,165,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(80,166,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(81,167,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(82,168,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(83,169,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(84,170,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(85,171,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(86,172,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(87,173,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(88,174,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(89,175,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(90,176,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(91,177,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(92,178,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(93,179,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(94,180,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(95,181,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(96,182,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(97,183,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(98,184,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(99,185,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(100,186,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(101,187,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(102,188,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(103,189,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(104,190,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(105,191,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(106,192,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(107,193,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(108,194,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(109,195,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(110,196,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(111,197,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(112,198,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(113,199,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(114,200,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47'),(115,201,1,'pending',NULL,NULL,NULL,NULL,NULL,'2026-05-24 22:21:47','2026-05-24 22:21:47');
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
) ENGINE=InnoDB AUTO_INCREMENT=19 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `student_distribution_sections`
--

LOCK TABLES `student_distribution_sections` WRITE;
/*!40000 ALTER TABLE `student_distribution_sections` DISABLE KEYS */;
INSERT INTO `student_distribution_sections` VALUES (1,'COMP4200 Introduction Section 1',2,NULL,'2026-05-20 13:03:36'),(2,'COMP4200 Introduction Section 2',1,NULL,'2026-05-20 13:03:36'),(3,'COMP4200 Introduction Section 3',5,NULL,'2026-05-20 13:03:36'),(4,'COMP4200 Section 01',3,2,'2026-05-24 22:16:43'),(5,'COMP4200 Section 02',4,2,'2026-05-24 22:16:43'),(6,'COMP4200 Section 03',5,2,'2026-05-24 22:16:43'),(7,'COMP4200 Section 04',6,2,'2026-05-24 22:16:43'),(8,'COMP4200 Section 05',7,2,'2026-05-24 22:16:43'),(9,'COMP4200 Section 06',8,2,'2026-05-24 22:16:43'),(10,'COMP4200 Section 07',9,2,'2026-05-24 22:16:43'),(11,'COMP4200 Section 08',10,2,'2026-05-24 22:16:43'),(12,'COMP4200 Section 09',11,2,'2026-05-24 22:16:43'),(13,'COMP4200 Section 10',13,2,'2026-05-24 22:16:43');
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
) ENGINE=InnoDB AUTO_INCREMENT=216 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `students`
--

LOCK TABLES `students` WRITE;
/*!40000 ALTER TABLE `students` DISABLE KEYS */;
INSERT INTO `students` VALUES (1,8,2022),(2,9,2022),(3,10,2022),(4,11,2022),(5,12,2022),(6,13,2021),(7,14,2022),(8,15,2022),(9,16,2021),(10,17,2022),(11,49,2022),(12,50,2022),(13,51,2022),(14,52,2022),(15,53,2022),(16,54,2022),(17,55,2022),(18,56,2022),(19,57,2022),(20,58,2022),(21,59,2022),(22,60,2022),(23,61,2022),(24,62,2022),(25,63,2022),(26,64,2022),(27,65,2022),(28,66,2022),(29,67,2022),(30,68,2022),(31,69,2022),(32,70,2022),(33,71,2022),(34,72,2022),(142,250,2022),(143,251,2022),(144,252,2022),(145,253,2022),(146,254,2022),(147,255,2022),(148,256,2022),(149,257,2022),(150,258,2022),(151,259,2022),(152,260,2022),(153,261,2022),(154,262,2022),(155,263,2022),(156,264,2022),(157,265,2022),(158,266,2022),(159,267,2022),(160,268,2022),(161,269,2022),(162,270,2022),(163,271,2022),(164,272,2022),(165,273,2022),(166,274,2022),(167,275,2022),(168,276,2022),(169,277,2022),(170,278,2022),(171,279,2022),(172,280,2022),(173,281,2022),(174,282,2022),(175,283,2022),(176,284,2022),(177,285,2022),(178,286,2022),(179,287,2022),(180,288,2022),(181,289,2022),(182,290,2022),(183,291,2022),(184,292,2022),(185,293,2022),(186,294,2022),(187,295,2022),(188,296,2022),(189,297,2022),(190,298,2022),(191,299,2022),(192,300,2022),(193,301,2022),(194,302,2022),(195,303,2022),(196,304,2022),(197,305,2022),(198,306,2022),(199,307,2022),(200,308,2022),(201,309,2022);
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
) ENGINE=InnoDB AUTO_INCREMENT=37 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `supervisor_notes`
--

LOCK TABLES `supervisor_notes` WRITE;
/*!40000 ALTER TABLE `supervisor_notes` DISABLE KEYS */;
INSERT INTO `supervisor_notes` VALUES (4,1,3,'Team is working diligently and progress is satisfactory. Presentation slides still need to be uploaded before the deadline.','on_track','2026-05-20 13:45:01'),(5,3,5,'No files have been uploaded for two weeks — requires immediate follow-up.','urgent','2026-05-20 13:45:01'),(6,2,4,'Progress is slightly slow but still within acceptable range. Awaiting source code update.','needs_follow_up','2026-05-20 13:45:01'),(7,1,3,'Team is working diligently and progress is satisfactory. Presentation slides still need to be uploaded before the deadline.','on_track','2026-05-20 13:57:21'),(8,3,5,'No files have been uploaded for two weeks — requires immediate follow-up.','urgent','2026-05-20 13:57:21'),(9,2,4,'Progress is slightly slow but still within acceptable range. Awaiting source code update.','needs_follow_up','2026-05-20 13:57:21'),(10,1,3,'Team is working diligently and progress is satisfactory. Presentation slides still need to be uploaded before the deadline.','on_track','2026-05-22 17:27:43'),(11,3,5,'No files have been uploaded for two weeks — requires immediate follow-up.','urgent','2026-05-22 17:27:43'),(12,2,4,'Progress is slightly slow but still within acceptable range. Awaiting source code update.','needs_follow_up','2026-05-22 17:27:43'),(13,1,3,'Team is working diligently and progress is satisfactory. Presentation slides still need to be uploaded before the deadline.','on_track','2026-05-22 17:30:09'),(14,3,5,'No files have been uploaded for two weeks — requires immediate follow-up.','urgent','2026-05-22 17:30:09'),(15,2,4,'Progress is slightly slow but still within acceptable range. Awaiting source code update.','needs_follow_up','2026-05-22 17:30:09'),(16,1,3,'Team is working diligently and progress is satisfactory. Presentation slides still need to be uploaded before the deadline.','on_track','2026-05-24 12:40:12'),(17,3,5,'No files have been uploaded for two weeks — requires immediate follow-up.','urgent','2026-05-24 12:40:12'),(18,2,4,'Progress is slightly slow but still within acceptable range. Awaiting source code update.','needs_follow_up','2026-05-24 12:40:12'),(19,1,3,'Team is working diligently and progress is satisfactory. Presentation slides still need to be uploaded before the deadline.','on_track','2026-05-24 19:44:30'),(20,3,5,'No files have been uploaded for two weeks — requires immediate follow-up.','urgent','2026-05-24 19:44:30'),(21,2,4,'Progress is slightly slow but still within acceptable range. Awaiting source code update.','needs_follow_up','2026-05-24 19:44:30'),(22,1,3,'Team is working diligently and progress is satisfactory. Presentation slides still need to be uploaded before the deadline.','on_track','2026-05-24 19:54:38'),(23,3,5,'No files have been uploaded for two weeks — requires immediate follow-up.','urgent','2026-05-24 19:54:38'),(24,2,4,'Progress is slightly slow but still within acceptable range. Awaiting source code update.','needs_follow_up','2026-05-24 19:54:38'),(25,1,3,'Team is working diligently and progress is satisfactory. Presentation slides still need to be uploaded before the deadline.','on_track','2026-05-24 20:13:39'),(26,3,5,'No files have been uploaded for two weeks — requires immediate follow-up.','urgent','2026-05-24 20:13:39'),(27,2,4,'Progress is slightly slow but still within acceptable range. Awaiting source code update.','needs_follow_up','2026-05-24 20:13:39'),(28,1,3,'Team is working diligently and progress is satisfactory. Presentation slides still need to be uploaded before the deadline.','on_track','2026-05-24 20:21:31'),(29,3,5,'No files have been uploaded for two weeks — requires immediate follow-up.','urgent','2026-05-24 20:21:31'),(30,2,4,'Progress is slightly slow but still within acceptable range. Awaiting source code update.','needs_follow_up','2026-05-24 20:21:31'),(31,1,3,'Team is working diligently and progress is satisfactory. Presentation slides still need to be uploaded before the deadline.','on_track','2026-05-24 22:16:42'),(32,3,5,'No files have been uploaded for two weeks — requires immediate follow-up.','urgent','2026-05-24 22:16:42'),(33,2,4,'Progress is slightly slow but still within acceptable range. Awaiting source code update.','needs_follow_up','2026-05-24 22:16:42'),(34,1,3,'Team is working diligently and progress is satisfactory. Presentation slides still need to be uploaded before the deadline.','on_track','2026-05-24 22:21:47'),(35,3,5,'No files have been uploaded for two weeks — requires immediate follow-up.','urgent','2026-05-24 22:21:47'),(36,2,4,'Progress is slightly slow but still within acceptable range. Awaiting source code update.','needs_follow_up','2026-05-24 22:21:47');
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
) ENGINE=InnoDB AUTO_INCREMENT=331 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES (1,'1001','Dr. Iyad Jaber','1001@birzeit.edu','$2b$12$EbPsSfvh6ScacL2l4uCkdOMwbfukrx0EdkL/0GBk/ntRtwRapvvBu','head_of_department','IJ',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(2,'1002','Dr. Ruba Awadallah','1002@birzeit.edu','$2b$12$l9Jz.shLtccTVJh5r700w.kCUlmwlba4YgUvs2HZGs2UBwuoonMci','coordinator','RA',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(3,'1003','Dr. Sobhi Ahmad','1003@birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','supervisor','SA',1,'2026-05-20 13:03:29','2026-05-24 22:16:43'),(4,'1004','Dr. Radi Jarrar','1004@birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','supervisor','RJ',1,'2026-05-20 13:03:29','2026-05-24 22:16:43'),(5,'1005','Dr. Abdullah Krakeh','1005@birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','supervisor','AK',1,'2026-05-20 13:03:29','2026-05-24 22:16:43'),(6,'1006','Dr. Mamoun Nawahdah','1006@birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','supervisor','MN',1,'2026-05-20 13:03:29','2026-05-24 22:16:43'),(7,'1007','Dr. Hafez Barghouthi','1007@birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','supervisor','HB',1,'2026-05-20 13:03:29','2026-05-24 22:16:43'),(8,'1220654','Rahaf Badwan','1220654@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','RB',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(9,'1220670','Amna Abu Muslim','1220670@students.birzeit.edu','$2b$12$1ONCgGY62binf5lUfYs6qekRIUhkUObqIs55tu.89rGMGOAsp0Llu','student','AM',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(10,'1220174','Tima Abd','1220174@students.birzeit.edu','$2b$12$OxHQ1TKrYWOQ6UUw8pN15.APXR8zjzAvrJkpUPpnkDtJFPPAo92Z.','student','TA',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(11,'1220110','Salma Al-Khatib','1220110@students.birzeit.edu','$2b$12$vMKQhyFzsLAXJkchac2KyeS4L2N.cw9AWHSCnwupz/cfc8s3Tf43a','student','SK',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(12,'1220087','Karim Odeh','1220087@students.birzeit.edu','$2b$12$aXSk8fIneFnOLmEnPH72CetVM9RwKecmo6YySgL8Td0V5M/ZNC6YC','student','KO',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(13,'1220500','Amjad Al-Rimawi','1220500@students.birzeit.edu','$2b$12$KBaKlbUt93mL9.oY1xrFQ.U.kCXt2eqAOdTZDdWOGiKWm0AOPsjem','student','AR',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(14,'1220600','Sara Musa','1220600@students.birzeit.edu','$2b$12$x46jpXoonqATaqjWSIZwvO4Mnx39j4YFAsl6TAxhw7m6xwbA4j3BK','student','SM',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(15,'1220700','Khaled Mansour','1220700@students.birzeit.edu','$2b$12$UZ02VkxW0l/XRWRu/T5ireQ5fiRfRdS0IiRzxe5RlfqnSLAe59A9O','student','KM',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(16,'1220800','Dana Ibrahim','1220800@students.birzeit.edu','$2b$12$km.HzoX0aw6nFjI2m3U8sezhKNDXZh7IBlpH.CEwqZx/ZSEv2DYqy','student','DI',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(17,'1220900','Mona Nassar','1220900@students.birzeit.edu','$2b$12$m/RTVrKRx.lsECFuFa6yguuR1rRxZO8i0QAxQun/7ojQZjq6M7D3G','student','MN',1,'2026-05-20 13:03:29','2026-05-20 13:03:29'),(18,'3006','Dr. Murad Njoum','murad.njoum@birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','supervisor','MN',1,'2026-05-20 13:03:31','2026-05-24 22:16:43'),(19,'3007','Dr. Adel Taweel','adel.taweel@birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','supervisor','AT',1,'2026-05-20 13:03:31','2026-05-24 22:16:43'),(20,'3008','Dr. Yousef Hassouneh','yousef.hassouneh@birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','supervisor','YH',1,'2026-05-20 13:03:31','2026-05-24 22:16:43'),(21,'3010','Dr. Bassem Alserafi','bassem.alserafi@birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','supervisor','BA',1,'2026-05-20 13:03:31','2026-05-24 22:16:43'),(22,'3012','Dr. Tasneem Zayt','tasneem.zayt@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','TZ',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(23,'3013','Dr. Samer Zein','samer.zein@birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','supervisor','SZ',1,'2026-05-20 13:03:31','2026-05-24 22:16:43'),(24,'3015','Dr. Abdullah Al-Natsheh','abdullah.alnatsheh@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','AN',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(25,'3016','Dr. Alaa Hasheesh','alaa.hasheesh@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','AH',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(26,'3017','Dr. Faisal Shehadeh','faisal.shehadeh@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','FS',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(27,'3018','Dr. Fadi Khalil','fadi.khalil@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','FK',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(28,'3019','Dr. Mohammad Helal','mohammad.helal@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','MH',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(29,'3020','Dr. Rashid Yousef','rashid.yousef@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','RY',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(30,'3021','Dr. Ehab Alshaer','ehab.alshaer@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','EA',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(31,'3023','Dr. Ahmad Fahl','ahmad.fahl@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','AF',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(32,'3024','Dr. Ahmad Sabbah','ahmad.sabbah@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','AS',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(33,'3025','Dr. Mohammad Alkhanafseh','mohammad.alkhanafseh@birzeit.edu','$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.','supervisor','MA',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(49,'1221001','Yousef Hamdan','1221001@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','YH',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(50,'1221002','Layan Daraghmeh','1221002@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','LD',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(51,'1221003','Noor Sawafta','1221003@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','NS',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(52,'1221004','Alaa Zakarneh','1221004@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','AZ',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(53,'1221005','Raneem Jaradat','1221005@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','RJ',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(54,'1221006','Malak Khoury','1221006@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','MK',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(55,'1221007','Hana Qasem','1221007@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','HQ',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(56,'1221008','Basil Jaber','1221008@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','BJ',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(57,'1221009','Jana Taqatqa','1221009@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','JT',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(58,'1221010','Omar Khatib','1221010@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','OK',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(59,'1221011','Reem Hammad','1221011@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','RH',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(60,'1221012','Yazan Abu Ayyash','1221012@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','YA',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(61,'1221013','Farah Odeh','1221013@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','FO',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(62,'1221014','Lina Barghouti','1221014@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','LB',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(63,'1221015','Mariam Salameh','1221015@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','MS',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(64,'1221016','Ali Shraim','1221016@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','AS',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(65,'1221017','Sama Dweikat','1221017@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','SD',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(66,'1221018','Husam Azzam','1221018@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','HA',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(67,'1221019','Aseel Masri','1221019@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','AM',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(68,'1221020','Rama Hamayel','1221020@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','RH',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(69,'1221021','Mahmoud Shtayyeh','1221021@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','MS',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(70,'1221022','Celine Nasser','1221022@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','CN',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(71,'1221023','Adam Zaid','1221023@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','AZ',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(72,'1221024','Shahd Abu Eisheh','1221024@students.birzeit.edu','$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.','student','SA',1,'2026-05-20 13:03:31','2026-05-20 13:03:31'),(250,'4200001','COMP4200 Student 01','4200001@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S01',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(251,'4200002','COMP4200 Student 02','4200002@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S02',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(252,'4200003','COMP4200 Student 03','4200003@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S03',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(253,'4200004','COMP4200 Student 04','4200004@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S04',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(254,'4200005','COMP4200 Student 05','4200005@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S05',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(255,'4200006','COMP4200 Student 06','4200006@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S06',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(256,'4200007','COMP4200 Student 07','4200007@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S07',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(257,'4200008','COMP4200 Student 08','4200008@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S08',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(258,'4200009','COMP4200 Student 09','4200009@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S09',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(259,'4200010','COMP4200 Student 10','4200010@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S10',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(260,'4200011','COMP4200 Student 11','4200011@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S11',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(261,'4200012','COMP4200 Student 12','4200012@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S12',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(262,'4200013','COMP4200 Student 13','4200013@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S13',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(263,'4200014','COMP4200 Student 14','4200014@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S14',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(264,'4200015','COMP4200 Student 15','4200015@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S15',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(265,'4200016','COMP4200 Student 16','4200016@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S16',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(266,'4200017','COMP4200 Student 17','4200017@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S17',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(267,'4200018','COMP4200 Student 18','4200018@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S18',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(268,'4200019','COMP4200 Student 19','4200019@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S19',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(269,'4200020','COMP4200 Student 20','4200020@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S20',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(270,'4200021','COMP4200 Student 21','4200021@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S21',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(271,'4200022','COMP4200 Student 22','4200022@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S22',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(272,'4200023','COMP4200 Student 23','4200023@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S23',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(273,'4200024','COMP4200 Student 24','4200024@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S24',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(274,'4200025','COMP4200 Student 25','4200025@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S25',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(275,'4200026','COMP4200 Student 26','4200026@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S26',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(276,'4200027','COMP4200 Student 27','4200027@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S27',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(277,'4200028','COMP4200 Student 28','4200028@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S28',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(278,'4200029','COMP4200 Student 29','4200029@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S29',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(279,'4200030','COMP4200 Student 30','4200030@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','S30',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(280,'4300001','COMP4300 Student 01','4300001@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G01',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(281,'4300002','COMP4300 Student 02','4300002@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G02',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(282,'4300003','COMP4300 Student 03','4300003@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G03',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(283,'4300004','COMP4300 Student 04','4300004@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G04',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(284,'4300005','COMP4300 Student 05','4300005@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G05',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(285,'4300006','COMP4300 Student 06','4300006@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G06',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(286,'4300007','COMP4300 Student 07','4300007@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G07',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(287,'4300008','COMP4300 Student 08','4300008@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G08',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(288,'4300009','COMP4300 Student 09','4300009@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G09',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(289,'4300010','COMP4300 Student 10','4300010@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G10',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(290,'4300011','COMP4300 Student 11','4300011@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G11',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(291,'4300012','COMP4300 Student 12','4300012@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G12',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(292,'4300013','COMP4300 Student 13','4300013@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G13',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(293,'4300014','COMP4300 Student 14','4300014@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G14',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(294,'4300015','COMP4300 Student 15','4300015@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G15',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(295,'4300016','COMP4300 Student 16','4300016@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G16',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(296,'4300017','COMP4300 Student 17','4300017@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G17',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(297,'4300018','COMP4300 Student 18','4300018@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G18',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(298,'4300019','COMP4300 Student 19','4300019@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G19',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(299,'4300020','COMP4300 Student 20','4300020@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G20',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(300,'4300021','COMP4300 Student 21','4300021@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G21',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(301,'4300022','COMP4300 Student 22','4300022@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G22',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(302,'4300023','COMP4300 Student 23','4300023@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G23',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(303,'4300024','COMP4300 Student 24','4300024@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G24',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(304,'4300025','COMP4300 Student 25','4300025@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G25',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(305,'4300026','COMP4300 Student 26','4300026@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G26',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(306,'4300027','COMP4300 Student 27','4300027@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G27',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(307,'4300028','COMP4300 Student 28','4300028@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G28',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(308,'4300029','COMP4300 Student 29','4300029@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G29',1,'2026-05-24 22:16:43','2026-05-24 22:16:43'),(309,'4300030','COMP4300 Student 30','4300030@students.birzeit.edu','$2b$05$D5fa/ZMO0l17xOixnQUsRuSI8bonQna5cdlPIvHt89jtwWb8zUd9S','student','G30',1,'2026-05-24 22:16:43','2026-05-24 22:16:43');
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
-- Temporary view structure for view `vw_distribution_real_groups`
--

DROP TABLE IF EXISTS `vw_distribution_real_groups`;
/*!50001 DROP VIEW IF EXISTS `vw_distribution_real_groups`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `vw_distribution_real_groups` AS SELECT 
 1 AS `project_id`,
 1 AS `group_name`,
 1 AS `team_members`,
 1 AS `idea_title`,
 1 AS `final_supervisor_id`,
 1 AS `final_supervisor_name`,
 1 AS `status`,
 1 AS `student_count`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `vw_evaluation_results_for_head`
--

DROP TABLE IF EXISTS `vw_evaluation_results_for_head`;
/*!50001 DROP VIEW IF EXISTS `vw_evaluation_results_for_head`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `vw_evaluation_results_for_head` AS SELECT 
 1 AS `result_id`,
 1 AS `course_scope`,
 1 AS `reference_id`,
 1 AS `report_score`,
 1 AS `supervisor_score`,
 1 AS `discussion_score`,
 1 AS `committee_score`,
 1 AS `final_score`,
 1 AS `decision`,
 1 AS `notes`,
 1 AS `workflow_status`,
 1 AS `supervisor_sent_to_head_at`,
 1 AS `head_published_at`,
 1 AS `supervisor_name`,
 1 AS `item_title`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `vw_evaluation_results_for_supervisors`
--

DROP TABLE IF EXISTS `vw_evaluation_results_for_supervisors`;
/*!50001 DROP VIEW IF EXISTS `vw_evaluation_results_for_supervisors`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `vw_evaluation_results_for_supervisors` AS SELECT 
 1 AS `result_id`,
 1 AS `course_scope`,
 1 AS `reference_id`,
 1 AS `report_score`,
 1 AS `supervisor_score`,
 1 AS `discussion_score`,
 1 AS `committee_score`,
 1 AS `final_score`,
 1 AS `decision`,
 1 AS `notes`,
 1 AS `workflow_status`,
 1 AS `sent_to_supervisor_at`,
 1 AS `supervisor_id`,
 1 AS `supervisor_name`,
 1 AS `item_title`*/;
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
-- Temporary view structure for view `vw_project_file_counts`
--

DROP TABLE IF EXISTS `vw_project_file_counts`;
/*!50001 DROP VIEW IF EXISTS `vw_project_file_counts`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `vw_project_file_counts` AS SELECT 
 1 AS `project_id`,
 1 AS `title`,
 1 AS `files_count`,
 1 AS `uploaded_files_count_from_table`*/;
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
-- Temporary view structure for view `vw_project_summary_with_files`
--

DROP TABLE IF EXISTS `vw_project_summary_with_files`;
/*!50001 DROP VIEW IF EXISTS `vw_project_summary_with_files`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `vw_project_summary_with_files` AS SELECT 
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
 1 AS `team_size`,
 1 AS `files_count`*/;
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
 1 AS `title`,
 1 AS `title_en`,
 1 AS `project_type`,
 1 AS `semester_id`,
 1 AS `supervisor_id`,
 1 AS `supervisor_name`,
 1 AS `status`,
 1 AS `submission_date`,
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
-- Final view structure for view `vw_distribution_real_groups`
--

/*!50001 DROP VIEW IF EXISTS `vw_distribution_real_groups`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `vw_distribution_real_groups` AS select `v`.`project_id` AS `project_id`,`v`.`section_name` AS `group_name`,`v`.`students` AS `team_members`,`v`.`title` AS `idea_title`,`v`.`supervisor_id` AS `final_supervisor_id`,`v`.`supervisor_name` AS `final_supervisor_name`,`v`.`status` AS `status`,`v`.`student_count` AS `student_count` from `vw_real_graduation_projects` `v` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `vw_evaluation_results_for_head`
--

/*!50001 DROP VIEW IF EXISTS `vw_evaluation_results_for_head`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `vw_evaluation_results_for_head` AS select `efr`.`result_id` AS `result_id`,`efr`.`course_scope` AS `course_scope`,`efr`.`reference_id` AS `reference_id`,`efr`.`report_score` AS `report_score`,`efr`.`supervisor_score` AS `supervisor_score`,`efr`.`discussion_score` AS `discussion_score`,`efr`.`committee_score` AS `committee_score`,`efr`.`final_score` AS `final_score`,`efr`.`decision` AS `decision`,`efr`.`notes` AS `notes`,`efr`.`workflow_status` AS `workflow_status`,`efr`.`supervisor_sent_to_head_at` AS `supervisor_sent_to_head_at`,`efr`.`head_published_at` AS `head_published_at`,`u_sup`.`full_name` AS `supervisor_name`,(case when (`efr`.`course_scope` = 'introduction') then `sec`.`section_name` else `p`.`title` end) AS `item_title` from ((((`evaluation_final_results` `efr` left join `student_distribution_sections` `sec` on(((`efr`.`course_scope` = 'introduction') and (`sec`.`section_id` = `efr`.`reference_id`)))) left join `projects` `p` on(((`efr`.`course_scope` = 'graduation_project') and (`p`.`project_id` = `efr`.`reference_id`)))) left join `faculty` `f_sup` on((`f_sup`.`faculty_id` = `efr`.`supervisor_id`))) left join `users` `u_sup` on((`u_sup`.`user_id` = `f_sup`.`user_id`))) where (`efr`.`workflow_status` in ('sent_to_head','published_to_students')) */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `vw_evaluation_results_for_supervisors`
--

/*!50001 DROP VIEW IF EXISTS `vw_evaluation_results_for_supervisors`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `vw_evaluation_results_for_supervisors` AS select `efr`.`result_id` AS `result_id`,`efr`.`course_scope` AS `course_scope`,`efr`.`reference_id` AS `reference_id`,`efr`.`report_score` AS `report_score`,`efr`.`supervisor_score` AS `supervisor_score`,`efr`.`discussion_score` AS `discussion_score`,`efr`.`committee_score` AS `committee_score`,`efr`.`final_score` AS `final_score`,`efr`.`decision` AS `decision`,`efr`.`notes` AS `notes`,`efr`.`workflow_status` AS `workflow_status`,`efr`.`sent_to_supervisor_at` AS `sent_to_supervisor_at`,`efr`.`supervisor_id` AS `supervisor_id`,`u_sup`.`full_name` AS `supervisor_name`,(case when (`efr`.`course_scope` = 'introduction') then `sec`.`section_name` else `p`.`title` end) AS `item_title` from ((((`evaluation_final_results` `efr` left join `student_distribution_sections` `sec` on(((`efr`.`course_scope` = 'introduction') and (`sec`.`section_id` = `efr`.`reference_id`)))) left join `projects` `p` on(((`efr`.`course_scope` = 'graduation_project') and (`p`.`project_id` = `efr`.`reference_id`)))) left join `faculty` `f_sup` on((`f_sup`.`faculty_id` = `efr`.`supervisor_id`))) left join `users` `u_sup` on((`u_sup`.`user_id` = `f_sup`.`user_id`))) where (`efr`.`workflow_status` in ('sent_to_supervisor','sent_to_head','published_to_students')) */;
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
-- Final view structure for view `vw_project_file_counts`
--

/*!50001 DROP VIEW IF EXISTS `vw_project_file_counts`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `vw_project_file_counts` AS select `p`.`project_id` AS `project_id`,`p`.`title` AS `title`,coalesce(`p`.`files_count`,0) AS `files_count`,count(`pf`.`file_id`) AS `uploaded_files_count_from_table` from (`projects` `p` left join `project_files` `pf` on(((`pf`.`project_id` = `p`.`project_id`) and ((`pf`.`upload_status` = 'uploaded') or (`pf`.`uploaded_at` is not null) or (`pf`.`file_data` is not null) or (coalesce(`pf`.`file_path`,'') <> ''))))) group by `p`.`project_id`,`p`.`title`,`p`.`files_count` */;
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
-- Final view structure for view `vw_project_summary_with_files`
--

/*!50001 DROP VIEW IF EXISTS `vw_project_summary_with_files`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `vw_project_summary_with_files` AS select `v`.`project_id` AS `project_id`,`v`.`title` AS `title`,`v`.`title_en` AS `title_en`,`v`.`project_type` AS `project_type`,`v`.`status` AS `status`,`v`.`submission_date` AS `submission_date`,`v`.`final_score` AS `final_score`,`v`.`academic_year` AS `academic_year`,`v`.`semester_number` AS `semester_number`,`v`.`course_code` AS `course_code`,`v`.`supervisor_name` AS `supervisor_name`,`v`.`supervisor_specialization` AS `supervisor_specialization`,`v`.`overall_progress` AS `overall_progress`,`v`.`report_progress` AS `report_progress`,`v`.`code_progress` AS `code_progress`,`v`.`slides_progress` AS `slides_progress`,`v`.`team_size` AS `team_size`,coalesce(`p`.`files_count`,0) AS `files_count` from (`vw_project_summary` `v` join `projects` `p` on((`p`.`project_id` = `v`.`project_id`))) */;
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
/*!50001 VIEW `vw_real_graduation_projects` AS select `p`.`project_id` AS `project_id`,coalesce(nullif(`p`.`group_name`,''),concat('Group ',`p`.`project_id`)) AS `section_name`,`p`.`title` AS `title`,`p`.`title_en` AS `title_en`,`p`.`project_type` AS `project_type`,`p`.`semester_id` AS `semester_id`,`p`.`supervisor_id` AS `supervisor_id`,`u_sup`.`full_name` AS `supervisor_name`,`p`.`status` AS `status`,`p`.`submission_date` AS `submission_date`,count(distinct `pm`.`student_id`) AS `student_count`,group_concat(distinct `u_st`.`full_name` order by `u_st`.`full_name` ASC separator ', ') AS `students` from ((((((`projects` `p` join `semesters` `sem` on((`sem`.`semester_id` = `p`.`semester_id`))) join `project_members` `pm` on((`pm`.`project_id` = `p`.`project_id`))) join `students` `st` on((`st`.`student_id` = `pm`.`student_id`))) join `users` `u_st` on((`u_st`.`user_id` = `st`.`user_id`))) left join `faculty` `f_sup` on((`f_sup`.`faculty_id` = `p`.`supervisor_id`))) left join `users` `u_sup` on((`u_sup`.`user_id` = `f_sup`.`user_id`))) where ((`sem`.`course_code` in ('COMP4300','COMP4201')) and (not((`p`.`title` like 'Committee Demo%')))) group by `p`.`project_id`,`p`.`group_name`,`p`.`title`,`p`.`title_en`,`p`.`project_type`,`p`.`semester_id`,`p`.`supervisor_id`,`u_sup`.`full_name`,`p`.`status`,`p`.`submission_date` */;
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

-- Dump completed on 2026-05-25  1:27:44
